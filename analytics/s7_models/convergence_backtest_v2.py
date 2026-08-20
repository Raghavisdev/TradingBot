"""
S7 V2 — REAL S6 EXECUTION REPLAY

Purpose
-------
Replay S7 rescue candidates through the actual S6 Moonshot Ladder
entry/exit implementation.

Temporal rules
--------------
1. S7 features/prediction are determined at signal T0.
2. We NEVER require a snapshot at T0.
3. If signal_price exists, it is the entry price at T0.
4. If signal_price is unavailable, the first valid snapshot STRICTLY
   AFTER T0 becomes the hypothetical execution snapshot.
5. All exit decisions use only snapshots strictly after execution.
6. Outcomes are not used to make trading decisions.
7. The real S6 ledger is never modified.
"""

import sqlite3
from pathlib import Path

import pandas as pd

from analytics.paper_lab.strategies import Strategy_S6_Moonshot_Ladder
from analytics.paper_lab.lab_portfolio import LabPortfolio


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

DB_PATH = ROOT / "database" / "trading.db"

TEST_PATH = (
    ROOT
    / "analytics"
    / "s7_dataset"
    / "s7_test.csv"
)

VALIDATION_PATH = (
    ROOT
    / "analytics"
    / "s7_dataset"
    / "s7_validation.csv"
)

OUTPUT_CSV = (
    ROOT
    / "analytics"
    / "s7_models"
    / "S7_V2_REAL_EXECUTION_REPLAY.csv"
)

OUTPUT_REPORT = (
    ROOT
    / "analytics"
    / "s7_models"
    / "S7_V2_REAL_EXECUTION_REPLAY.txt"
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def parse_ts(value):
    """
    Convert ISO timestamp or numeric timestamp into Unix seconds.
    """
    if value is None:
        return None

    try:
        value = float(value)

        # Already Unix epoch.
        if value > 1_000_000_000:
            return value
    except (TypeError, ValueError):
        pass

    try:
        return pd.Timestamp(value).timestamp()
    except Exception:
        return None


def load_signal(cur, signal_id):
    row = cur.execute(
        """
        SELECT
            signal_id,
            timestamp,
            source,
            symbol,
            name,
            contract,
            telegram_message,
            signal_market_cap,
            signal_price,
            gt_score,
            decision,
            final_score,
            bot_version,
            bought,
            buy_blocked_by,
            tracking_started,
            tracking_completed,
            decision_reason
        FROM signals
        WHERE signal_id = ?
        LIMIT 1
        """,
        (str(signal_id),),
    ).fetchone()

    if not row:
        return None

    cols = [
        "signal_id",
        "timestamp",
        "source",
        "symbol",
        "name",
        "contract",
        "telegram_message",
        "signal_market_cap",
        "signal_price",
        "gt_score",
        "decision",
        "final_score",
        "bot_version",
        "bought",
        "buy_blocked_by",
        "tracking_started",
        "tracking_completed",
        "decision_reason",
    ]

    return dict(zip(cols, row))


# ============================================================
# SNAPSHOT HELPERS
# ============================================================

SNAPSHOT_COLS = [
    "signal_id",
    "timestamp",
    "market_cap",
    "price",
    "liquidity",
    "volume",
    "buys",
    "sells",
    "holders",
    "market_health",
    "exit_action",
    "exit_confidence",
]


def get_first_post_t0_snapshot(cur, signal_id, t0):
    """
    IMPORTANT:

    There is intentionally NO <= T0 query here.

    If no signal_price exists, execution begins at the first
    valid market snapshot strictly after T0.
    """

    row = cur.execute(
        """
        SELECT
            signal_id,
            timestamp,
            market_cap,
            price,
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

    return dict(zip(SNAPSHOT_COLS, row))


def get_entry_price_and_time(cur, signal, t0):
    """
    Entry priority:

    1. Real signal_price if available.
    2. Otherwise first valid snapshot strictly after T0.

    We never fabricate a T0 price.
    """

    try:
        price = float(signal.get("signal_price") or 0.0)
    except (TypeError, ValueError):
        price = 0.0

    if price > 0:
        return price, float(t0)

    snapshot = get_first_post_t0_snapshot(
        cur,
        signal["signal_id"],
        t0,
    )

    if not snapshot:
        return None, None

    return (
        float(snapshot["price"]),
        float(snapshot["timestamp"]),
    )


def get_future_snapshots(cur, signal_id, entry_time):
    """
    Return only snapshots strictly AFTER the execution snapshot.
    """

    rows = cur.execute(
        """
        SELECT
            signal_id,
            timestamp,
            market_cap,
            price,
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

    return [
        dict(zip(SNAPSHOT_COLS, row))
        for row in rows
    ]


# ============================================================
# S6 ENTRY SIGNAL
# ============================================================

def make_s6_entry_signal(
    signal,
    entry_snapshot,
    entry_price,
    entry_time,
):
    """
    Construct the signal dictionary expected by
    Strategy_S6_Moonshot_Ladder.evaluate_entry().

    Original signal/T0 information is preserved.

    Execution-time market fields come from the first executable
    snapshot when signal_price was unavailable.
    """

    result = dict(signal)

    result["signal_time"] = float(entry_time)
    result["signal_price"] = float(entry_price)

    signal_mc = float(
        signal.get("signal_market_cap") or 0.0
    )

    if signal_mc <= 0 and entry_snapshot:
        signal_mc = float(
            entry_snapshot.get("market_cap") or 0.0
        )

    result["signal_market_cap"] = signal_mc

    if entry_snapshot:

        for key in [
            "liquidity",
            "volume",
            "buys",
            "sells",
            "holders",
            "market_health",
        ]:
            result[key] = entry_snapshot.get(key)

        buys = float(
            entry_snapshot.get("buys") or 0.0
        )

        sells = float(
            entry_snapshot.get("sells") or 0.0
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
# POSITION SNAPSHOT UPDATE
# ============================================================

def update_position_from_snapshot(
    pos,
    snapshot,
):
    """
    Update the position's market state using the same information
    available to the strategy at that historical snapshot.

    This is deliberately defensive because different Paper Lab
    versions can expose slightly different portfolio APIs.
    """

    try:
        price = float(
            snapshot.get("price") or 0.0
        )
    except (TypeError, ValueError):
        price = 0.0

    try:
        mc = float(
            snapshot.get("market_cap") or 0.0
        )
    except (TypeError, ValueError):
        mc = 0.0

    try:
        pos.update_snapshot(snapshot)
        return
    except AttributeError:
        pass

    # Fallback for portfolio implementations without
    # update_snapshot().
    try:
        pos.current_price = price
    except Exception:
        pass

    try:
        pos.current_mc = mc
    except Exception:
        pass


# ============================================================
# REAL S6 REPLAY
# ============================================================

def replay_candidate(
    cur,
    strategy,
    row,
):
    """
    Replay one S7 rescue candidate through the real S6 mechanics.

    Temporal sequence:

        S7 T0
          |
          v
        first executable snapshot AFTER T0
          |
          v
        S6 evaluate_entry()
          |
          v
        subsequent historical snapshots
          |
          v
        S6 evaluate_exit()
          |
          v
        realized P&L
    """

    signal_id = str(
        row["signal_id"]
    )

    signal = load_signal(
        cur,
        signal_id,
    )

    if not signal:
        return {
            "signal_id": signal_id,
            "status": "NO_SIGNAL",
            "pnl": 0.0,
        }

    t0 = parse_ts(
        signal["timestamp"]
    )

    if t0 is None:
        return {
            "signal_id": signal_id,
            "status": "INVALID_T0",
            "pnl": 0.0,
        }

    # --------------------------------------------------------
    # Determine execution point.
    #
    # CRITICAL:
    # We DO NOT require a T0 snapshot.
    # --------------------------------------------------------

    entry_snapshot = None

    signal_price = signal.get(
        "signal_price"
    )

    try:
        signal_price_value = float(
            signal_price or 0.0
        )
    except (TypeError, ValueError):
        signal_price_value = 0.0

    if signal_price_value <= 0:

        entry_snapshot = (
            get_first_post_t0_snapshot(
                cur,
                signal_id,
                t0,
            )
        )

        if not entry_snapshot:
            return {
                "signal_id": signal_id,
                "status": "NO_POST_T0_SNAPSHOT",
                "pnl": 0.0,
            }

    entry_price, entry_time = (
        get_entry_price_and_time(
            cur,
            signal,
            t0,
        )
    )

    if (
        entry_price is None
        or entry_price <= 0
        or entry_time is None
    ):
        return {
            "signal_id": signal_id,
            "status": "NO_ENTRY_PRICE",
            "pnl": 0.0,
        }

    # If signal_price existed, fetch the execution snapshot
    # only when possible. It is not required for a T0-priced
    # signal.
    if entry_snapshot is None:

        row_snapshot = cur.execute(
            """
            SELECT
                signal_id,
                timestamp,
                market_cap,
                price,
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
              AND CAST(price AS REAL) > 0
            ORDER BY CAST(timestamp AS REAL) ASC
            LIMIT 1
            """,
            (
                signal_id,
                float(entry_time),
            ),
        ).fetchone()

        if row_snapshot:
            entry_snapshot = dict(
                zip(
                    SNAPSHOT_COLS,
                    row_snapshot,
                )
            )

    # --------------------------------------------------------
    # Build the exact S6 entry signal.
    # --------------------------------------------------------

    entry_signal = make_s6_entry_signal(
        signal,
        entry_snapshot,
        entry_price,
        entry_time,
    )

    # --------------------------------------------------------
    # Isolated $500 rescue sleeve.
    # --------------------------------------------------------

    portfolio = LabPortfolio(
        strategy_id="S7_RESCUE_S6_REPLAY",
        initial_cash=500.0,
        max_open=8,
        min_cash=2.0,
    )

    # REAL S6 entry-sizing logic.
    amount = strategy.evaluate_entry(
        entry_signal,
        portfolio,
    )

    if amount is None:
        amount = 0.0

    amount = float(amount)

    if amount <= 0:
        return {
            "signal_id": signal_id,
            "status": "S6_ENTRY_REJECTED",
            "pnl": 0.0,
            "entry_time": entry_time,
            "entry_price": entry_price,
        }

    entry_mc = float(
        entry_signal.get(
            "signal_market_cap"
        )
        or 0.0
    )

    pos = portfolio.open_position(
        trade_id=(
            f"S7_REPLAY_{signal_id[:8]}"
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
        invested=amount,
    )

    if not pos:
        return {
            "signal_id": signal_id,
            "status": "PORTFOLIO_REJECTED",
            "pnl": 0.0,
        }

    # --------------------------------------------------------
    # Historical snapshots AFTER entry.
    # --------------------------------------------------------

    snapshots = get_future_snapshots(
        cur,
        signal_id,
        entry_time,
    )

    if not snapshots:
        return {
            "signal_id": signal_id,
            "status": "NO_FUTURE_SNAPSHOTS",
            "pnl": 0.0,
            "invested": amount,
            "entry_time": entry_time,
            "entry_price": entry_price,
        }

    exit_reason = ""
    forced_horizon_close = False

    # --------------------------------------------------------
    # REAL S6 exit mechanics.
    # --------------------------------------------------------

    for snap in snapshots:

        try:
            ts = float(
                snap["timestamp"]
            )
        except (TypeError, ValueError):
            continue

        try:
            price = float(
                snap.get("price") or 0.0
            )
        except (TypeError, ValueError):
            continue

        try:
            mc = float(
                snap.get("market_cap") or 0.0
            )
        except (TypeError, ValueError):
            mc = 0.0

        if price <= 0:
            continue

        update_position_from_snapshot(
            pos,
            snap,
        )

        action, pct, reason = (
            strategy.evaluate_exit(
                snap,
                pos,
            )
        )

        # ----------------------------------------------------
        # Full close
        # ----------------------------------------------------

        if action == "SELL_ALL":

            portfolio.close_position(
                pos,
                reason,
                ts,
                price,
                mc,
            )

            exit_reason = str(
                reason or "SELL_ALL"
            )

            break

        # ----------------------------------------------------
        # Partial close.
        #
        # The S6 strategy may return SELL_PCT.
        # We intentionally pass the percentage directly to
        # the real LabPortfolio implementation.
        # ----------------------------------------------------

        if action == "SELL_PCT" and pct > 0:

            portfolio.close_position_by_partial_sell(
                pos,
                float(pct),
                reason,
                ts,
                price,
                mc,
            )

            exit_reason = str(
                reason or "SELL_PCT"
            )

            if pos.remaining_pct <= 0.01:
                break

    # --------------------------------------------------------
    # Horizon close.
    #
    # If S6 never closed the position during the available
    # historical path, close it at the final observed snapshot.
    #
    # This is NOT an outcome-table shortcut.
    # It uses an actual recorded market snapshot.
    # --------------------------------------------------------

    if pos.status == "OPEN":

        last = snapshots[-1]

        try:
            ts = float(
                last["timestamp"]
            )
        except (TypeError, ValueError):
            ts = entry_time

        try:
            price = float(
                last.get("price") or 0.0
            )
        except (TypeError, ValueError):
            price = 0.0

        try:
            mc = float(
                last.get("market_cap") or 0.0
            )
        except (TypeError, ValueError):
            mc = 0.0

        if price > 0:

            update_position_from_snapshot(
                pos,
                last,
            )

            portfolio.close_position(
                pos,
                "Replay horizon close",
                ts,
                price,
                mc,
            )

            exit_reason = (
                "Replay horizon close"
            )

            forced_horizon_close = True

    realized_pnl = float(
        getattr(
            pos,
            "realized_pnl",
            0.0,
        )
        or 0.0
    )

    invested = float(
        getattr(
            pos,
            "invested",
            amount,
        )
        or amount
    )

    realized_pct = (
        realized_pnl
        / invested
        * 100.0
        if invested > 0
        else 0.0
    )

    return {
        "signal_id": signal_id,
        "status": (
            "CLOSED"
            if pos.status == "CLOSED"
            else str(pos.status)
        ),
        "invested": invested,
        "realized_pnl": realized_pnl,
        "realized_pct": realized_pct,
        "mfe": float(
            getattr(
                pos,
                "mfe",
                0.0,
            )
            or 0.0
        ),
        "mae": float(
            getattr(
                pos,
                "mae",
                0.0,
            )
            or 0.0
        ),
        "peak_multiple": float(
            getattr(
                pos,
                "peak_multiple",
                1.0,
            )
            or 1.0
        ),
        "remaining_pct": float(
            getattr(
                pos,
                "remaining_pct",
                0.0,
            )
            or 0.0
        ),
        "exit_reason": exit_reason,
        "forced_horizon_close": (
            forced_horizon_close
        ),
        "snapshots": len(snapshots),
        "entry_time": entry_time,
        "entry_price": entry_price,
        "entry_mc": entry_mc,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("S7 V2 — REAL S6 EXECUTION REPLAY")
    print("=" * 60)

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    if not TEST_PATH.exists():
        raise FileNotFoundError(
            f"Test dataset not found: {TEST_PATH}"
        )

    test = pd.read_csv(
        TEST_PATH
    )

    validation = None

    if VALIDATION_PATH.exists():
        validation = pd.read_csv(
            VALIDATION_PATH
        )

    # --------------------------------------------------------
    # Identify S7 rescue candidates.
    #
    # Prefer the predictions already produced by the existing
    # convergence pipeline when available.
    # --------------------------------------------------------

    candidate_columns = [
        "s7_rescue",
        "rescue",
        "accepted",
    ]

    candidate_col = None

    for col in candidate_columns:
        if col in test.columns:
            candidate_col = col
            break

    if candidate_col is not None:

        rescue_mask = (
            test[candidate_col]
            .fillna(False)
            .astype(bool)
        )

        candidates = test[
            rescue_mask
        ].copy()

    else:

        # Fall back to the three candidates selected by the
        # already completed validation/test convergence run.
        #
        # These are NOT selected using future outcomes here.
        known_candidates = {
            "e0654005-2fe2-468f-acd2-07b55976f1de",
            "4110afe6-e00c-4840-932e-1086c2ca6ff8",
            "fb89ba0a-bba6-430f-87db-2da1f529d00b",
        }

        candidates = test[
            test["signal_id"]
            .astype(str)
            .isin(known_candidates)
        ].copy()

    # --------------------------------------------------------
    # Threshold display.
    #
    # The thresholds were previously selected from validation.
    # We do not tune anything on final test here.
    # --------------------------------------------------------

    opportunity_threshold = 0.448748
    rug_threshold = 0.882631

    print(
        f"Validation opportunity threshold: "
        f"{opportunity_threshold:.4f}"
    )

    print(
        f"Validation rug threshold:         "
        f"{rug_threshold:.4f}"
    )

    print()
    print(
        f"Final test signals:       {len(test)}"
    )

    non_buy_count = 0

    if "decision" in test.columns:
        non_buy_count = int(
            (
                ~test["decision"]
                .astype(str)
                .str.upper()
                .isin(["BUY", "STRONG BUY"])
            ).sum()
        )

    print(
        f"S6 non-BUY candidates:    "
        f"{non_buy_count}"
    )

    print(
        f"S7 rescue candidates:     "
        f"{len(candidates)}"
    )

    # --------------------------------------------------------
    # Real S6 strategy.
    # --------------------------------------------------------

    strategy = (
        Strategy_S6_Moonshot_Ladder()
    )

    results = []

    con = sqlite3.connect(
        str(DB_PATH)
    )

    cur = con.cursor()

    try:

        for _, row in candidates.iterrows():

            signal_id = str(
                row["signal_id"]
            )

            print(
                f"\nReplaying "
                f"{signal_id[:8]}..."
            )

            result = replay_candidate(
                cur,
                strategy,
                row,
            )

            results.append(result)

            print(
                f"  status: "
                f"{result.get('status')}"
            )

            if "realized_pnl" in result:
                print(
                    f"  invested: "
                    f"${result.get('invested', 0):.4f}"
                )

                print(
                    f"  realized P&L: "
                    f"${result.get('realized_pnl', 0):+.4f}"
                )

    finally:
        con.close()

    # --------------------------------------------------------
    # Results dataframe.
    # --------------------------------------------------------

    results_df = pd.DataFrame(
        results
    )

    if results_df.empty:
        results_df = pd.DataFrame(
            columns=[
                "signal_id",
                "status",
                "invested",
                "realized_pnl",
                "realized_pct",
                "mfe",
                "mae",
                "peak_multiple",
                "remaining_pct",
                "exit_reason",
                "forced_horizon_close",
                "snapshots",
                "entry_time",
                "entry_price",
                "entry_mc",
            ]
        )

    results_df.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    successfully_replayed = int(
        (
            results_df["status"]
            == "CLOSED"
        ).sum()
    )

    total_invested = float(
        results_df["invested"]
        .fillna(0.0)
        .sum()
    )

    total_pnl = float(
        results_df["realized_pnl"]
        .fillna(0.0)
        .sum()
    )

    winning = int(
        (
            results_df["realized_pnl"]
            > 0
        ).sum()
    )

    losing = int(
        (
            results_df["realized_pnl"]
            < 0
        ).sum()
    )

    forced = int(
        results_df[
            "forced_horizon_close"
        ]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    roi = (
        total_pnl
        / total_invested
        * 100.0
        if total_invested > 0
        else 0.0
    )

    # --------------------------------------------------------
    # REAL S6 baseline from recorded paper-lab trades.
    # --------------------------------------------------------

    con = sqlite3.connect(
        str(DB_PATH)
    )

    try:

        test_ids = set(
            test["signal_id"]
            .astype(str)
        )

        placeholders = ",".join(
            "?"
            for _ in test_ids
        )

        if test_ids:

            baseline_query = f"""
                SELECT
                    signal_id,
                    invested,
                    realized_pnl
                FROM paper_lab_trades
                WHERE strategy_id =
                    'S6_Moonshot_Ladder'
                  AND signal_id IN (
                    {placeholders}
                  )
            """

            baseline = pd.read_sql_query(
                baseline_query,
                con,
                params=list(test_ids),
            )

        else:
            baseline = pd.DataFrame()

    finally:
        con.close()

    s6_pnl = float(
        baseline["realized_pnl"]
        .fillna(0.0)
        .sum()
    ) if not baseline.empty else 0.0

    combined_pnl = (
        s6_pnl
        + total_pnl
    )

    # --------------------------------------------------------
    # Report.
    # --------------------------------------------------------

    report = []

    report.append(
        "============================================================"
    )
    report.append(
        "S7 V2 — REAL S6 EXECUTION REPLAY"
    )
    report.append(
        "============================================================"
    )
    report.append("")

    report.append(
        "MODEL / TEMPORAL GATE"
    )
    report.append(
        f"- Final test rows: {len(test)}"
    )
    report.append(
        f"- S6 non-BUY candidates: {non_buy_count}"
    )
    report.append(
        f"- S7 rescue candidates: {len(candidates)}"
    )
    report.append(
        f"- Opportunity threshold: "
        f"{opportunity_threshold:.6f}"
    )
    report.append(
        f"- Rug threshold: "
        f"{rug_threshold:.6f}"
    )
    report.append("")

    report.append(
        "RESCUE REPLAY"
    )
    report.append(
        f"- Successfully replayed: "
        f"{successfully_replayed}"
    )
    report.append(
        f"- Total invested: "
        f"${total_invested:.4f}"
    )
    report.append(
        f"- Realized P&L: "
        f"${total_pnl:+.4f}"
    )
    report.append(
        f"- Return on invested capital: "
        f"{roi:.2f}%"
    )
    report.append(
        f"- Winning rescues: {winning}"
    )
    report.append(
        f"- Losing rescues: {losing}"
    )
    report.append(
        f"- Forced horizon closes: {forced}"
    )
    report.append("")

    report.append(
        "REAL S6 EXECUTION BASELINE"
    )
    report.append(
        f"- Actual S6 final-test P&L: "
        f"${s6_pnl:+.4f}"
    )
    report.append("")

    report.append(
        "S6 + S7 ECONOMIC CONVERGENCE"
    )
    report.append(
        f"- S6 baseline P&L: "
        f"${s6_pnl:+.4f}"
    )
    report.append(
        f"- S7 incremental P&L: "
        f"${total_pnl:+.4f}"
    )
    report.append(
        f"- Combined P&L: "
        f"${combined_pnl:+.4f}"
    )
    report.append(
        f"- Incremental lift: "
        f"${total_pnl:+.4f}"
    )
    report.append("")

    report.append(
        "IMPORTANT INTERPRETATION"
    )
    report.append(
        "- S6 baseline comes from actual recorded "
        "S6_Moonshot_Ladder trades."
    )
    report.append(
        "- S7 rescue execution uses the real "
        "S6 entry/exit strategy."
    )
    report.append(
        "- Missing T0 snapshots are NOT treated as "
        "missing trades."
    )
    report.append(
        "- When signal_price is unavailable, "
        "the first valid post-T0 snapshot is used."
    )
    report.append(
        "- Future snapshots are used only after "
        "the hypothetical entry."
    )
    report.append(
        "- Outcomes are not used to trigger trades."
    )
    report.append(
        "- The actual S6 ledger is never modified."
    )
    report.append(
        "- This replay uses an isolated $500 rescue sleeve."
    )
    report.append("")

    report_text = "\n".join(
        report
    )

    print()
    print(report_text)

    OUTPUT_REPORT.write_text(
        report_text,
        encoding="utf-8",
    )

    print()
    print(
        f"Trade-level results: "
        f"{OUTPUT_CSV}"
    )

    print(
        f"Report: "
        f"{OUTPUT_REPORT}"
    )


if __name__ == "__main__":
    main()
