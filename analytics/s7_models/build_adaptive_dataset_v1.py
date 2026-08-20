import sqlite3
import numpy as np
import pandas as pd


DB = "database/trading.db"

OUT = (
    "analytics/s7_models/"
    "adaptive_training_dataset_v1.csv"
)


def safe_float(x):
    try:
        if x is None:
            return np.nan
        return float(x)
    except Exception:
        return np.nan


def main():

    con = sqlite3.connect(DB)

    print("=" * 90)
    print("S7 ADAPTIVE TRAINING DATASET V1")
    print("=" * 90)

    trades = pd.read_sql_query(
        """
        SELECT
            id,
            trade_id,
            strategy_id,
            strategy_version,
            signal_id,
            symbol,
            contract,

            entry_time,
            entry_price,
            entry_market_cap,
            invested,

            exit_time,
            exit_price,
            exit_market_cap,

            exit_reason,

            realized_pnl,
            realized_pct,

            mfe,
            mae,

            fees,
            slippage,

            fired_levels,
            highest_stop_pnl,
            peak_multiple

        FROM paper_lab_trades

        WHERE strategy_id = 'S6_Moonshot_Ladder'
          AND status = 'CLOSED'

        ORDER BY entry_time ASC
        """,
        con,
    )

    print(f"S6 closed trades: {len(trades)}")

    if trades.empty:
        print("No S6 closed trades found.")
        con.close()
        return

    # ------------------------------------------------------------
    # SIGNAL FEATURES
    # ------------------------------------------------------------

    signals = pd.read_sql_query(
        """
        SELECT *
        FROM signals
        """,
        con,
    )

    print(f"Signals available: {len(signals)}")

    # ------------------------------------------------------------
    # SNAPSHOTS
    # ------------------------------------------------------------

    snapshots = pd.read_sql_query(
        """
        SELECT
            signal_id,
            CAST(timestamp AS REAL) AS timestamp,
            CAST(price AS REAL) AS price,
            CAST(market_cap AS REAL) AS market_cap,
            CAST(liquidity AS REAL) AS liquidity,
            CAST(volume AS REAL) AS volume,
            CAST(buys AS REAL) AS buys,
            CAST(sells AS REAL) AS sells,
            CAST(holders AS REAL) AS holders,
            CAST(market_health AS REAL) AS market_health
        FROM snapshots
        ORDER BY signal_id, timestamp
        """,
        con,
    )

    print(f"Snapshots available: {len(snapshots)}")

    con.close()

    # ============================================================
    # SIGNAL JOIN
    # ============================================================

    if "signal_id" not in signals.columns:
        raise RuntimeError(
            "signals table does not contain signal_id"
        )

    merged = trades.merge(
        signals,
        on="signal_id",
        how="left",
        suffixes=("", "_signal"),
    )

    print(
        "After signal join:",
        len(merged)
    )

    # ============================================================
    # BUILD T0 + EARLY FEATURES
    # ============================================================

    rows = []

    for _, trade in merged.iterrows():

        signal_id = trade["signal_id"]

        snap = snapshots[
            snapshots["signal_id"].astype(str)
            == str(signal_id)
        ].copy()

        if snap.empty:
            continue

        snap = snap.sort_values("timestamp")

        entry_time = safe_float(
            trade["entry_time"]
        )

        if not np.isfinite(entry_time):
            continue

        # First executable snapshot at/after entry.
        executable = snap[
            (snap["timestamp"] >= entry_time)
            & (snap["price"] > 0)
        ]

        if executable.empty:
            continue

        t0 = executable.iloc[0]

        record = {
            "trade_id": trade["trade_id"],
            "signal_id": signal_id,
            "symbol": trade["symbol"],
            "contract": trade["contract"],

            # ----------------------------------------------------
            # ENTRY / SIGNAL FEATURES
            # ----------------------------------------------------

            "gt_score": safe_float(
                trade.get("gt_score")
            ),

            "final_score": safe_float(
                trade.get("final_score")
            ),

            "signal_market_cap": safe_float(
                trade.get("signal_market_cap")
            ),

            "t0_price": safe_float(
                t0["price"]
            ),

            "t0_market_cap": safe_float(
                t0["market_cap"]
            ),

            "t0_liquidity": safe_float(
                t0["liquidity"]
            ),

            "t0_volume": safe_float(
                t0["volume"]
            ),

            "t0_buys": safe_float(
                t0["buys"]
            ),

            "t0_sells": safe_float(
                t0["sells"]
            ),

            "t0_holders": safe_float(
                t0["holders"]
            ),

            "t0_market_health": safe_float(
                t0["market_health"]
            ),
        }

        # ========================================================
        # DERIVED T0 FEATURES
        # ========================================================

        buys = record["t0_buys"]
        sells = record["t0_sells"]

        if (
            np.isfinite(buys)
            and np.isfinite(sells)
            and sells > 0
        ):
            record["t0_bs_ratio"] = buys / sells
        else:
            record["t0_bs_ratio"] = np.nan

        # ========================================================
        # EARLY MOMENTUM
        #
        # Use only snapshots after entry.
        # Never use the final outcome.
        # ========================================================

        future = snap[
            snap["timestamp"] > entry_time
        ].copy()

        if not future.empty:

            first_early = future.iloc[0]

            record["early_price_change_pct"] = (
                (
                    safe_float(first_early["price"])
                    / record["t0_price"]
                ) - 1.0
            ) * 100.0

            if record["t0_volume"] > 0:

                record["early_volume_change_pct"] = (
                    (
                        safe_float(
                            first_early["volume"]
                        )
                        / record["t0_volume"]
                    ) - 1.0
                ) * 100.0

            else:
                record["early_volume_change_pct"] = np.nan

            if record["t0_market_cap"] > 0:

                record["early_mc_change_pct"] = (
                    (
                        safe_float(
                            first_early["market_cap"]
                        )
                        / record["t0_market_cap"]
                    ) - 1.0
                ) * 100.0

            else:
                record["early_mc_change_pct"] = np.nan

            early_buys = safe_float(
                first_early["buys"]
            )

            early_sells = safe_float(
                first_early["sells"]
            )

            if (
                np.isfinite(early_buys)
                and np.isfinite(early_sells)
                and early_sells > 0
            ):
                record["early_bs_ratio"] = (
                    early_buys /
                    early_sells
                )
            else:
                record["early_bs_ratio"] = np.nan

        else:

            record["early_price_change_pct"] = np.nan
            record["early_volume_change_pct"] = np.nan
            record["early_mc_change_pct"] = np.nan
            record["early_bs_ratio"] = np.nan

        # ========================================================
        # CAPITAL / EXECUTION INFORMATION
        # ========================================================

        record["invested"] = safe_float(
            trade["invested"]
        )

        record["entry_time"] = entry_time

        # ========================================================
        # FUTURE LABELS
        #
        # NEVER USE THESE AS ENTRY FEATURES.
        # ========================================================

        record["realized_pnl"] = safe_float(
            trade["realized_pnl"]
        )

        record["realized_pct"] = safe_float(
            trade["realized_pct"]
        )

        record["mfe"] = safe_float(
            trade["mfe"]
        )

        record["mae"] = safe_float(
            trade["mae"]
        )

        record["peak_multiple"] = safe_float(
            trade["peak_multiple"]
        )

        record["fees"] = safe_float(
            trade["fees"]
        )

        record["slippage"] = safe_float(
            trade["slippage"]
        )

        record["exit_reason"] = (
            trade["exit_reason"]
        )

        # --------------------------------------------------------
        # Runner labels
        # --------------------------------------------------------

        mfe = record["mfe"]

        record["runner_50"] = (
            int(mfe >= 50)
            if np.isfinite(mfe)
            else 0
        )

        record["runner_100"] = (
            int(mfe >= 100)
            if np.isfinite(mfe)
            else 0
        )

        record["runner_200"] = (
            int(mfe >= 200)
            if np.isfinite(mfe)
            else 0
        )

        rows.append(record)

    dataset = pd.DataFrame(rows)

    print()
    print("=" * 90)
    print("DATASET SUMMARY")
    print("=" * 90)

    print(
        "Usable rows:",
        len(dataset)
    )

    if dataset.empty:
        print(
            "No usable rows were constructed."
        )
        return

    print()
    print(
        "Runner counts:"
    )

    print(
        "50% :",
        int(dataset["runner_50"].sum())
    )

    print(
        "100%:",
        int(dataset["runner_100"].sum())
    )

    print(
        "200%:",
        int(dataset["runner_200"].sum())
    )

    print()
    print(
        "Date range:"
    )

    print(
        pd.to_datetime(
            dataset["entry_time"],
            unit="s",
            errors="coerce",
        ).agg(
            ["min", "max"]
        )
    )

    print()
    print(
        "Columns:"
    )

    for col in dataset.columns:
        print(
            " ",
            col
        )

    dataset.to_csv(
        OUT,
        index=False
    )

    print()
    print("=" * 90)
    print("SAVED")
    print("=" * 90)

    print(OUT)


if __name__ == "__main__":
    main()
