import sqlite3
import numpy as np
import pandas as pd

DB = "database/trading.db"
OUT = "analytics/s7_models/adaptive_training_dataset_v2.csv"


def f(x):
    try:
        if x is None:
            return np.nan
        return float(x)
    except Exception:
        return np.nan


def snapshot_at_or_after(snapshots, target):
    x = snapshots[snapshots["timestamp"] >= target]
    if x.empty:
        return None
    return x.iloc[0]


def add_state(record, prefix, snap, t0):
    if snap is None:
        return

    price = f(snap["price"])
    mc = f(snap["market_cap"])
    vol = f(snap["volume"])
    liq = f(snap["liquidity"])
    buys = f(snap["buys"])
    sells = f(snap["sells"])

    record[f"{prefix}_delay_sec"] = (
        f(snap["timestamp"]) - t0
    )

    record[f"{prefix}_price"] = price
    record[f"{prefix}_market_cap"] = mc
    record[f"{prefix}_liquidity"] = liq
    record[f"{prefix}_volume"] = vol
    record[f"{prefix}_buys"] = buys
    record[f"{prefix}_sells"] = sells
    record[f"{prefix}_holders"] = f(snap["holders"])
    record[f"{prefix}_market_health"] = f(
        snap["market_health"]
    )

    if record["t0_price"] > 0 and price > 0:
        record[f"{prefix}_price_change_pct"] = (
            price / record["t0_price"] - 1
        ) * 100
    else:
        record[f"{prefix}_price_change_pct"] = np.nan

    if record["t0_market_cap"] > 0 and mc > 0:
        record[f"{prefix}_mc_change_pct"] = (
            mc / record["t0_market_cap"] - 1
        ) * 100
    else:
        record[f"{prefix}_mc_change_pct"] = np.nan

    if record["t0_volume"] > 0 and vol >= 0:
        record[f"{prefix}_volume_change_pct"] = (
            vol / record["t0_volume"] - 1
        ) * 100
    else:
        record[f"{prefix}_volume_change_pct"] = np.nan

    if buys >= 0 and sells > 0:
        record[f"{prefix}_bs_ratio"] = (
            buys / sells
        )
    else:
        record[f"{prefix}_bs_ratio"] = np.nan


def main():

    con = sqlite3.connect(DB)

    trades = pd.read_sql_query(
        """
        SELECT *
        FROM paper_lab_trades
        WHERE strategy_id = 'S6_Moonshot_Ladder'
          AND status = 'CLOSED'
        ORDER BY entry_time ASC
        """,
        con,
    )

    signals = pd.read_sql_query(
        "SELECT * FROM signals",
        con,
    )

    snapshots = pd.read_sql_query(
        """
        SELECT
            signal_id,
            CAST(timestamp AS REAL) timestamp,
            CAST(price AS REAL) price,
            CAST(market_cap AS REAL) market_cap,
            CAST(liquidity AS REAL) liquidity,
            CAST(volume AS REAL) volume,
            CAST(buys AS REAL) buys,
            CAST(sells AS REAL) sells,
            CAST(holders AS REAL) holders,
            CAST(market_health AS REAL) market_health
        FROM snapshots
        ORDER BY signal_id, timestamp
        """,
        con,
    )

    con.close()

    merged = trades.merge(
        signals,
        on="signal_id",
        how="left",
        suffixes=("", "_signal"),
    )

    rows = []

    for _, trade in merged.iterrows():

        sid = str(trade["signal_id"])

        s = snapshots[
            snapshots.signal_id.astype(str) == sid
        ].copy()

        if s.empty:
            continue

        s = s.sort_values("timestamp")

        t0 = f(trade["entry_time"])

        executable = s[
            (s["timestamp"] >= t0)
            & (s["price"] > 0)
        ]

        if executable.empty:
            continue

        t0snap = executable.iloc[0]

        record = {
            "trade_id": trade["trade_id"],
            "signal_id": sid,
            "symbol": trade["symbol"],
            "contract": trade["contract"],

            "entry_time": t0,
            "invested": f(trade["invested"]),

            "gt_score": f(trade.get("gt_score")),
            "final_score": f(trade.get("final_score")),
            "signal_market_cap": f(
                trade.get("signal_market_cap")
            ),

            "t0_price": f(t0snap["price"]),
            "t0_market_cap": f(t0snap["market_cap"]),
            "t0_liquidity": f(t0snap["liquidity"]),
            "t0_volume": f(t0snap["volume"]),
            "t0_buys": f(t0snap["buys"]),
            "t0_sells": f(t0snap["sells"]),
            "t0_holders": f(t0snap["holders"]),
            "t0_market_health": f(
                t0snap["market_health"]
            ),
        }

        if record["t0_sells"] > 0:
            record["t0_bs_ratio"] = (
                record["t0_buys"]
                / record["t0_sells"]
            )
        else:
            record["t0_bs_ratio"] = np.nan

        # Actual observable states.
        #
        # These are NOT claimed to be exact timestamps.
        add_state(
            record,
            "first",
            t0snap,
            t0,
        )

        add_state(
            record,
            "early_10_20s",
            snapshot_at_or_after(
                s,
                t0 + 10,
            ),
            t0,
        )

        add_state(
            record,
            "early_20_30s",
            snapshot_at_or_after(
                s,
                t0 + 20,
            ),
            t0,
        )

        add_state(
            record,
            "early_30_40s",
            snapshot_at_or_after(
                s,
                t0 + 30,
            ),
            t0,
        )

        # Future-only labels.
        mfe = f(trade["mfe"])

        record["realized_pnl"] = f(
            trade["realized_pnl"]
        )
        record["realized_pct"] = f(
            trade["realized_pct"]
        )
        record["mfe"] = mfe
        record["mae"] = f(trade["mae"])
        record["peak_multiple"] = f(
            trade["peak_multiple"]
        )

        record["runner_50"] = int(
            np.isfinite(mfe) and mfe >= 50
        )

        record["runner_100"] = int(
            np.isfinite(mfe) and mfe >= 100
        )

        record["runner_200"] = int(
            np.isfinite(mfe) and mfe >= 200
        )

        record["exit_reason"] = trade[
            "exit_reason"
        ]

        rows.append(record)

    df = pd.DataFrame(rows)

    df.to_csv(
        OUT,
        index=False,
    )

    print("=" * 80)
    print("S7 ADAPTIVE DATASET V2")
    print("=" * 80)
    print("Rows:", len(df))
    print("Columns:", len(df.columns))
    print("Saved:", OUT)

    print()
    print("Runner labels:")
    print("50% :", int(df.runner_50.sum()))
    print("100%:", int(df.runner_100.sum()))
    print("200%:", int(df.runner_200.sum()))

    print()
    print("Observable-state availability:")

    for prefix in [
        "first",
        "early_10_20s",
        "early_20_30s",
        "early_30_40s",
    ]:
        col = f"{prefix}_price"

        available = (
            df[col].notna().sum()
        )

        print(
            f"{prefix:15s}: "
            f"{available}/{len(df)}"
        )


if __name__ == "__main__":
    main()
