import sqlite3
import numpy as np
import pandas as pd

DB = "database/trading.db"

# ============================================================
# IMPORT REAL S6 ENGINE
# ============================================================

from analytics.paper_lab.strategies import (
    Strategy_S6_Moonshot_Ladder,
)

from analytics.paper_lab.lab_portfolio import (
    LabPortfolio,
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_signal(con, signal_id):

    row = con.execute(
        """
        SELECT
            signal_id,
            timestamp,
            symbol,
            contract,
            signal_price,
            signal_market_cap,
            gt_score,
            final_score,
            decision
        FROM signals
        WHERE signal_id = ?
        """,
        (str(signal_id),),
    ).fetchone()

    if not row:
        return None

    cols = [
        "signal_id",
        "timestamp",
        "symbol",
        "contract",
        "signal_price",
        "signal_market_cap",
        "gt_score",
        "final_score",
        "decision",
    ]

    return dict(zip(cols, row))


def parse_timestamp(value):

    if value is None:
        return None

    try:
        return pd.to_datetime(value).timestamp()
    except Exception:

        try:
            return float(value)
        except Exception:
            return None


def get_entry_snapshot(con, signal_id, t0):

    row = con.execute(
        """
        SELECT
            CAST(timestamp AS REAL),
            price,
            market_cap,
            liquidity,
            volume,
            buys,
            sells,
            holders,
            market_health
        FROM snapshots
        WHERE signal_id = ?
          AND CAST(timestamp AS REAL) >= ?
          AND CAST(price AS REAL) > 0
        ORDER BY CAST(timestamp AS REAL) ASC
        LIMIT 1
        """,
        (
            str(signal_id),
            float(t0),
        ),
    ).fetchone()

    if not row:
        return None

    cols = [
        "timestamp",
        "price",
        "market_cap",
        "liquidity",
        "volume",
        "buys",
        "sells",
        "holders",
        "market_health",
    ]

    return dict(zip(cols, row))


def get_future_snapshots(con, signal_id, entry_time):

    rows = con.execute(
        """
        SELECT
            CAST(timestamp AS REAL),
            price,
            market_cap,
            liquidity,
            volume,
            buys,
            sells,
            holders,
            market_health,
            exit_action,
            exit_confidence
        FROM snapshots
        WHERE signal_id = ?
          AND CAST(timestamp AS REAL) > ?
        ORDER BY CAST(timestamp AS REAL) ASC
        """,
        (
            str(signal_id),
            float(entry_time),
        ),
    ).fetchall()

    cols = [
        "timestamp",
        "price",
        "market_cap",
        "liquidity",
        "volume",
        "buys",
        "sells",
        "holders",
        "market_health",
        "exit_action",
        "exit_confidence",
    ]

    return [
        dict(zip(cols, row))
        for row in rows
    ]


# ============================================================
# BUILD ENTRY SIGNAL
# ============================================================

def build_entry_signal(signal, snapshot):

    result = dict(signal)

    result["liquidity"] = snapshot.get("liquidity")
    result["volume"] = snapshot.get("volume")
    result["buys"] = snapshot.get("buys")
    result["sells"] = snapshot.get("sells")
    result["holders"] = snapshot.get("holders")

    result["market_cap"] = snapshot.get(
        "market_cap"
    )

    result["market_health"] = snapshot.get(
        "market_health"
    )

    buys = float(
        snapshot.get("buys") or 0.0
    )

    sells = float(
        snapshot.get("sells") or 0.0
    )

    if sells > 0:

        result["buy_sell_ratio"] = (
            buys / sells
        )

    elif buys > 0:

        result["buy_sell_ratio"] = min(
            buys,
            3.0,
        )

    else:

        result["buy_sell_ratio"] = 1.0

    return result


# ============================================================
# REGIME DEFINITIONS
# ============================================================

def regime_matches(name, row):

    mc = float(
        row.get("market_cap") or 0.0
    )

    volume = float(
        row.get("volume") or 0.0
    )

    buys = float(
        row.get("buys") or 0.0
    )

    sells = float(
        row.get("sells") or 0.0
    )

    if sells > 0:

        bs = buys / sells

    elif buys > 0:

        bs = min(buys, 3.0)

    else:

        bs = 1.0

    fs = float(
        row.get("final_score") or 0.0
    )

    if name == "BASELINE":
        return True

    if name == "MC_GE_40K_VOL_GE_30K":

        return (
            mc >= 40000
            and volume >= 30000
        )

    if name == "MC_40_50K":

        return (
            40000 <= mc < 50000
        )

    if name == "FS_GE_66":

        return fs >= 66

    if name == "BS_1_0_1_2":

        return (
            1.0 <= bs < 1.2
        )

    if name == "VOL_GE_30K":

        return volume >= 30000

    if name == "MC_GE_50K":

        return mc >= 50000

    if name == "FS_GE_68":

        return fs >= 68

    if name == "MC_LT_40K_VOL_LT_20K_BS_GE_1_FS_GE_64":

        return (
            mc < 40000
            and volume < 20000
            and bs >= 1.0
            and fs >= 64
        )

    return False


REGIMES = [
    "BASELINE",
    "MC_GE_40K_VOL_GE_30K",
    "MC_40_50K",
    "FS_GE_66",
    "BS_1_0_1_2",
    "VOL_GE_30K",
    "MC_GE_50K",
    "FS_GE_68",
    "MC_LT_40K_VOL_LT_20K_BS_GE_1_FS_GE_64",
]


# ============================================================
# ACTUAL S6 TRADED IDS
# ============================================================

def get_s6_traded_ids(con):

    rows = con.execute(
        """
        SELECT DISTINCT signal_id
        FROM paper_lab_trades
        WHERE strategy_id = 'S6_Moonshot_Ladder'
        """
    ).fetchall()

    return {
        str(r[0])
        for r in rows
        if r[0] is not None
    }


# ============================================================
# REPLAY ONE SIGNAL
# ============================================================

def replay_signal(
    con,
    strategy,
    signal_id,
):

    signal = get_signal(
        con,
        signal_id,
    )

    if signal is None:

        return {
            "status": "NO_SIGNAL",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
            "mfe": 0.0,
        }

    t0 = parse_timestamp(
        signal.get("timestamp")
    )

    if t0 is None:

        return {
            "status": "INVALID_T0",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
            "mfe": 0.0,
        }

    entry_snapshot = get_entry_snapshot(
        con,
        signal_id,
        t0,
    )

    if entry_snapshot is None:

        return {
            "status": "NO_ENTRY_SNAPSHOT",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
            "mfe": 0.0,
        }

    entry_signal = build_entry_signal(
        signal,
        entry_snapshot,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # We use a fresh isolated portfolio for every counterfactual
    # signal. This measures the economic behavior of S6 itself.
    # --------------------------------------------------------

    portfolio = LabPortfolio(
        strategy_id="S6_COUNTERFACTUAL",
        initial_cash=500.0,
        max_open=8,
        min_cash=2.0,
    )

    amount = strategy.evaluate_entry(
        entry_signal,
        portfolio,
    )

    if amount <= 0:

        return {
            "status": "S6_ENTRY_REJECTED",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
            "mfe": 0.0,
        }

    entry_time = float(
        entry_snapshot["timestamp"]
    )

    entry_price = float(
        entry_snapshot["price"]
    )

    entry_mc = float(
        entry_snapshot["market_cap"] or 0.0
    )

    pos = portfolio.open_position(
        trade_id=(
            f"CF_{signal_id[:12]}"
        ),
        strategy_version=(
            strategy.strategy_version
        ),
        signal_id=signal_id,
        symbol=(
            signal.get("symbol")
            or "?"
        ),
        contract=(
            signal.get("contract")
            or ""
        ),
        entry_time=entry_time,
        entry_price=entry_price,
        entry_mc=entry_mc,
        invested=float(amount),
    )

    if not pos:

        return {
            "status": "PORTFOLIO_REJECTED",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
            "mfe": 0.0,
        }

    future = get_future_snapshots(
        con,
        signal_id,
        entry_time,
    )

    closed = False

    for snapshot in future:

        # Update position state BEFORE evaluating exit.
        # This is important because S6 trailing logic depends
        # on highest observed P&L.
        pos.update_snapshot(
            snapshot
        )

        action, payload, reason = (
            strategy.evaluate_exit(
                snapshot,
                pos,
            )
        )

        ts = float(
            snapshot["timestamp"]
        )

        price = float(
            snapshot["price"] or 0.0
        )

        mc = float(
            snapshot["market_cap"] or 0.0
        )

        # ----------------------------------------------------
        # Full exit
        # ----------------------------------------------------

        if action == "SELL_ALL":

            portfolio.close_position(
                pos,
                reason,
                ts,
                price,
                mc,
            )

            closed = True
            break

        # ----------------------------------------------------
        # S6 ladder exit
        #
        # S6 returns:
        # ("SELL_PCT_LADDER", crossed, reason)
        #
        # crossed is a list:
        # [(20.0, 20.0), (50.0, 10.0), ...]
        # ----------------------------------------------------

        if action == "SELL_PCT_LADDER":

            crossed = payload

            if crossed:

                for target_pct, sell_pct in crossed:

                    if sell_pct <= 0:
                        continue

                    if pos.remaining_pct <= 0.01:
                        break

                    portfolio.close_position_by_partial_sell(
                        pos,
                        sell_pct,
                        reason,
                        ts,
                        price,
                        mc,
                    )

                    # Mark ladder level as fired.
                    pos.fired_ladder_levels.add(
                        target_pct
                    )

                if pos.remaining_pct <= 0.01:

                    closed = True
                    break

        # ----------------------------------------------------
        # Compatibility with older strategy implementation
        # ----------------------------------------------------

        elif action == "SELL_PCT":

            if payload and payload > 0:

                portfolio.close_position_by_partial_sell(
                    pos,
                    payload,
                    reason,
                    ts,
                    price,
                    mc,
                )

                if pos.remaining_pct <= 0.01:

                    closed = True
                    break

    # ========================================================
    # HORIZON CLOSE
    # ========================================================

    if (
        not closed
        and pos.status == "OPEN"
        and future
    ):

        last = future[-1]

        portfolio.close_position(
            pos,
            "COUNTERFACTUAL_HORIZON_CLOSE",
            float(last["timestamp"]),
            float(last["price"] or 0.0),
            float(last["market_cap"] or 0.0),
        )

    invested = float(
        pos.invested
    )

    pnl = float(
        pos.realized_pnl
    )

    realized_pct = (
        pnl / invested * 100.0
        if invested > 0
        else 0.0
    )

    return {
        "status": "CLOSED",
        "invested": invested,
        "pnl": pnl,
        "realized_pct": realized_pct,
        "mfe": float(
            getattr(pos, "highest_pnl_pct", 0.0)
        ),
    }


# ============================================================
# LOAD SIGNALS
# ============================================================

def load_signals(con):

    query = """
    SELECT
        s.signal_id,
        s.symbol,
        CAST(s.timestamp AS REAL) AS signal_time,
        CAST(s.gt_score AS REAL) AS gt_score,
        CAST(s.final_score AS REAL) AS final_score,
        CAST(s.signal_market_cap AS REAL) AS signal_market_cap
    FROM signals s
    WHERE s.signal_id IS NOT NULL
    """

    df = pd.read_sql_query(
        query,
        con,
    )

    df["signal_id"] = (
        df["signal_id"].astype(str)
    )

    return df


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 90)
    print("S6 COUNTERFACTUAL ECONOMIC REGIME REPLAY V1")
    print("=" * 90)

    con = sqlite3.connect(
        DB
    )

    signals = load_signals(
        con
    )

    s6_ids = get_s6_traded_ids(
        con
    )

    print()
    print("Total signals:", len(signals))
    print("Historical S6 trades:", len(s6_ids))

    strategy = (
        Strategy_S6_Moonshot_Ladder()
    )

    # --------------------------------------------------------
    # Build entry snapshots first.
    # --------------------------------------------------------

    records = []

    print()
    print("Building executable T0 population...")

    for i, row in signals.iterrows():

        sid = str(
            row["signal_id"]
        )

        signal = get_signal(
            con,
            sid,
        )

        if signal is None:
            continue

        t0 = parse_timestamp(
            signal.get("timestamp")
        )

        if t0 is None:
            continue

        snap = get_entry_snapshot(
            con,
            sid,
            t0,
        )

        if snap is None:
            continue

        record = {
            "signal_id": sid,
            "symbol": row["symbol"],
            "gt_score": row["gt_score"],
            "final_score": row["final_score"],
            "signal_market_cap": row[
                "signal_market_cap"
            ],
            "market_cap": snap.get(
                "market_cap"
            ),
            "volume": snap.get(
                "volume"
            ),
            "buys": snap.get(
                "buys"
            ),
            "sells": snap.get(
                "sells"
            ),
            "liquidity": snap.get(
                "liquidity"
            ),
            "s6_traded": (
                sid in s6_ids
            ),
        }

        records.append(
            record
        )

    df = pd.DataFrame(
        records
    )

    print(
        "Executable signals:",
        len(df),
    )

    # --------------------------------------------------------
    # Candidate regime discovery.
    #
    # IMPORTANT:
    # No outcome information is used here.
    # --------------------------------------------------------

    print()
    print("=" * 90)
    print("ENTRY REGIME POPULATION")
    print("=" * 90)

    for regime in REGIMES:

        mask = df.apply(
            lambda r:
                regime_matches(
                    regime,
                    r,
                ),
            axis=1,
        )

        subset = df[
            mask
        ]

        print(
            f"{regime:<48} "
            f"N={len(subset):4d} "
            f"S6={int(subset['s6_traded'].sum()):4d} "
            f"counterfactual={len(subset)-int(subset['s6_traded'].sum()):4d}"
        )

    # --------------------------------------------------------
    # Counterfactual replay
    #
    # We replay genuinely S6-untraded signals only.
    #
    # This prevents double-counting actual S6 trades.
    # --------------------------------------------------------

    all_results = []

    for regime in REGIMES:

        mask = df.apply(
            lambda r:
                regime_matches(
                    regime,
                    r,
                ),
            axis=1,
        )

        candidates = df[
            mask
        ]

        # Only signals S6 did NOT historically trade.
        candidates = candidates[
            ~candidates["s6_traded"]
        ]

        print()
        print("=" * 90)
        print(
            f"REPLAYING: {regime}"
        )
        print(
            f"Counterfactual candidates: {len(candidates)}"
        )
        print("=" * 90)

        if candidates.empty:
            continue

        for n, (_, row) in enumerate(
            candidates.iterrows(),
            start=1,
        ):

            sid = str(
                row["signal_id"]
            )

            result = replay_signal(
                con,
                strategy,
                sid,
            )

            result.update(
                {
                    "regime": regime,
                    "signal_id": sid,
                    "symbol": row[
                        "symbol"
                    ],
                    "final_score": row[
                        "final_score"
                    ],
                    "market_cap": row[
                        "market_cap"
                    ],
                    "volume": row[
                        "volume"
                    ],
                    "liquidity": row[
                        "liquidity"
                    ],
                }
            )

            all_results.append(
                result
            )

            if n % 25 == 0:
                print(
                    f"  processed {n}/{len(candidates)}"
                )

    results = pd.DataFrame(
        all_results
    )

    if results.empty:

        print(
            "No counterfactual results."
        )

        return

    # ========================================================
    # ECONOMIC SUMMARY
    # ========================================================

    print()
    print("=" * 90)
    print("COUNTERFACTUAL S6 ECONOMIC RESULTS")
    print("=" * 90)

    summary = []

    for regime in REGIMES:

        r = results[
            results["regime"]
            == regime
        ].copy()

        if r.empty:
            continue

        accepted = r[
            r["status"]
            == "CLOSED"
        ]

        if accepted.empty:

            summary.append(
                {
                    "regime": regime,
                    "N": len(r),
                    "entered": 0,
                    "rejected": len(r),
                    "invested": 0.0,
                    "pnl": 0.0,
                    "ROI": 0.0,
                    "win_rate": 0.0,
                    "avg_pnl": 0.0,
                }
            )

            continue

        invested = (
            accepted["invested"]
            .sum()
        )

        pnl = (
            accepted["pnl"]
            .sum()
        )

        wins = int(
            (
                accepted["pnl"]
                > 0
            ).sum()
        )

        summary.append(
            {
                "regime": regime,
                "N": len(r),
                "entered": len(accepted),
                "rejected": len(r) - len(accepted),
                "invested": invested,
                "pnl": pnl,
                "ROI": (
                    pnl / invested * 100.0
                    if invested > 0
                    else 0.0
                ),
                "win_rate": (
                    wins / len(accepted) * 100.0
                ),
                "avg_pnl": (
                    pnl / len(accepted)
                ),
            }
        )

    summary_df = pd.DataFrame(
        summary
    )

    print(
        summary_df.to_string(
            index=False,
            formatters={
                "invested": "{:.2f}".format,
                "pnl": "{:+.4f}".format,
                "ROI": "{:+.2f}%".format,
                "win_rate": "{:.2f}%".format,
                "avg_pnl": "{:+.4f}".format,
            },
        )
    )

    # ========================================================
    # IMPORTANT COMPARISON
    # ========================================================

    print()
    print("=" * 90)
    print("INTERPRETATION")
    print("=" * 90)

    print(
        """
These results measure the ECONOMIC effect of applying each
entry regime before the REAL S6 execution engine.

A regime is interesting only if:

1. It produces positive counterfactual P&L.
2. ROI is better than the broad baseline.
3. It has enough trades to be meaningful.
4. The result is not dependent on one giant winner.
5. It survives an untouched time-period test.

Do NOT modify S6 from this output alone.
"""
    )

    # ========================================================
    # SAVE
    # ========================================================

    out_summary = (
        "analytics/s7_models/"
        "counterfactual_s6_regime_summary_v1.csv"
    )

    out_trades = (
        "analytics/s7_models/"
        "counterfactual_s6_regime_trades_v1.csv"
    )

    summary_df.to_csv(
        out_summary,
        index=False,
    )

    results.to_csv(
        out_trades,
        index=False,
    )

    print()
    print("Saved:")
    print(out_summary)
    print(out_trades)


if __name__ == "__main__":
    main()
