import sqlite3
import pandas as pd
import numpy as np

from analytics.paper_lab.strategies import Strategy_S6_Moonshot_Ladder


DB = "database/trading.db"

TRAIN_CSV = "analytics/s7_dataset/s7_train.csv"
VAL_CSV = "analytics/s7_dataset/s7_validation.csv"
TEST_CSV = "analytics/s7_dataset/s7_test.csv"

OUTPUT_CSV = "analytics/s7_models/S6_GATE_CALIBRATION.csv"


# ============================================================
# HELPERS
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        value = float(value)

        if not np.isfinite(value):
            return default

        return value

    except Exception:
        return default


def load_ids(path):
    df = pd.read_csv(path)

    if "signal_id" not in df.columns:
        raise RuntimeError(
            f"{path} does not contain signal_id"
        )

    return set(
        df["signal_id"]
        .astype(str)
        .tolist()
    )


def classify_dataset(signal_id, train_ids, val_ids, test_ids):

    sid = str(signal_id)

    if sid in train_ids:
        return "TRAIN"

    if sid in val_ids:
        return "VALIDATION"

    if sid in test_ids:
        return "TEST"

    return "OTHER"


# ============================================================
# LOAD S6 TRADES
# ============================================================

def load_s6_trades():

    con = sqlite3.connect(DB)

    query = """
        SELECT
            p.signal_id,
            p.trade_id,
            p.strategy_version,
            p.entry_time,
            p.entry_price,
            p.entry_market_cap,
            p.invested,
            p.exit_time,
            p.exit_price,
            p.realized_pnl,
            p.realized_pct,
            p.mfe,
            p.mae,
            p.exit_reason,
            p.peak_multiple,

            s.timestamp AS signal_timestamp,
            s.source,
            s.symbol,
            s.name,
            s.contract,
            s.signal_market_cap,
            s.signal_price,
            s.gt_score,
            s.decision,
            s.final_score,
            s.bought

        FROM paper_lab_trades p

        LEFT JOIN signals s
            ON s.signal_id = p.signal_id

        WHERE p.strategy_id = 'S6_Moonshot_Ladder'
          AND p.status = 'CLOSED'

        ORDER BY p.entry_time ASC
    """

    df = pd.read_sql_query(query, con)

    con.close()

    return df


# ============================================================
# LOAD SNAPSHOTS SAFELY
#
# We deliberately avoid a correlated SQL query.
# SQLite reads the relevant snapshots once and Python finds
# the nearest snapshot to each trade entry.
# ============================================================

def load_relevant_snapshots(signal_ids):

    if not signal_ids:
        return pd.DataFrame()

    con = sqlite3.connect(DB)

    placeholders = ",".join(
        ["?"] * len(signal_ids)
    )

    query = f"""
        SELECT
            signal_id,
            CAST(timestamp AS REAL) AS snapshot_time,
            market_cap,
            price,
            liquidity,
            volume,
            buys,
            sells,
            holders,
            market_health
        FROM snapshots
        WHERE signal_id IN ({placeholders})
        ORDER BY signal_id, snapshot_time
    """

    df = pd.read_sql_query(
        query,
        con,
        params=list(signal_ids)
    )

    con.close()

    return df


# ============================================================
# FIND ENTRY SNAPSHOT
# ============================================================

def attach_entry_snapshots(trades, snapshots):

    trades = trades.copy()

    fields = [
        "snap_market_cap",
        "snap_price",
        "liquidity",
        "volume",
        "buys",
        "sells",
        "holders",
        "market_health",
    ]

    for field in fields:
        trades[field] = np.nan

    if snapshots.empty:
        return trades

    grouped = {
        sid: group
        for sid, group
        in snapshots.groupby("signal_id")
    }

    for idx, trade in trades.iterrows():

        sid = str(trade["signal_id"])

        if sid not in grouped:
            continue

        snaps = grouped[sid]

        entry_time = safe_float(
            trade["entry_time"],
            np.nan
        )

        if not np.isfinite(entry_time):
            continue

        times = snaps["snapshot_time"].to_numpy()

        if len(times) == 0:
            continue

        # Prefer the latest snapshot at or before entry.
        before = snaps[
            snaps["snapshot_time"] <= entry_time
        ]

        if not before.empty:

            selected = before.iloc[-1]

        else:

            # If no snapshot exists before entry,
            # use the first snapshot after entry.
            selected = snaps.iloc[0]

        trades.at[idx, "snap_market_cap"] = safe_float(
            selected["market_cap"],
            np.nan
        )

        trades.at[idx, "snap_price"] = safe_float(
            selected["price"],
            np.nan
        )

        trades.at[idx, "liquidity"] = safe_float(
            selected["liquidity"],
            np.nan
        )

        trades.at[idx, "volume"] = safe_float(
            selected["volume"],
            np.nan
        )

        trades.at[idx, "buys"] = safe_float(
            selected["buys"],
            np.nan
        )

        trades.at[idx, "sells"] = safe_float(
            selected["sells"],
            np.nan
        )

        trades.at[idx, "holders"] = safe_float(
            selected["holders"],
            np.nan
        )

        trades.at[idx, "market_health"] = safe_float(
            selected["market_health"],
            np.nan
        )

    return trades


# ============================================================
# RECONSTRUCT ACTUAL S6 SIGNAL
# ============================================================

def make_signal(row):

    signal = {
        "signal_id": str(row["signal_id"]),

        "valid": True,

        "symbol": row["symbol"],

        "final_score": row["final_score"],

        "gt_score": row["gt_score"],

        "signal_market_cap": row["signal_market_cap"],

        "snap_mc": row["snap_market_cap"],

        "liquidity": row["liquidity"],

        "volume": row["volume"],

        "buys": row["buys"],

        "sells": row["sells"],

        "holders": row["holders"],

        "market_health": row["market_health"],
    }

    # If buys/sells exist, this is the same input path
    # used by S6's current compute_entry_quality().
    if (
        pd.notna(row["buys"])
        and pd.notna(row["sells"])
    ):
        sells = safe_float(row["sells"])

        if sells > 0:
            signal["buy_sell_ratio"] = (
                safe_float(row["buys"]) / sells
            )

    return signal


# ============================================================
# CALCULATE ACTUAL S6 Q
# ============================================================

def calculate_q(row, strategy):

    signal = make_signal(row)

    try:

        q = strategy.compute_entry_quality(
            signal
        )

        return safe_float(
            q,
            np.nan
        )

    except Exception as e:

        print(
            f"[WARNING] Q calculation failed "
            f"for {row['signal_id']}: {e}"
        )

        return np.nan


# ============================================================
# BASIC SUMMARY
# ============================================================

def summarize(df, title):

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    if df.empty:

        print("No trades.")
        return

    wins = (
        df["realized_pnl"] > 0
    ).sum()

    losses = (
        df["realized_pnl"] <= 0
    ).sum()

    invested = safe_float(
        df["invested"].sum()
    )

    pnl = safe_float(
        df["realized_pnl"].sum()
    )

    print(
        f"Trades:              {len(df)}"
    )

    print(
        f"Winners:             {wins}"
    )

    print(
        f"Losers:              {losses}"
    )

    print(
        f"Invested:            ${invested:.4f}"
    )

    print(
        f"Realized P&L:        ${pnl:+.4f}"
    )

    if len(df) > 0:

        print(
            f"Win rate:            "
            f"{wins / len(df) * 100:.2f}%"
        )

        print(
            f"Average P&L:         "
            f"${df['realized_pnl'].mean():+.4f}"
        )

        print(
            f"Average realized %:  "
            f"{df['realized_pct'].mean():+.2f}%"
        )

        print(
            f"Average MFE:         "
            f"{df['mfe'].mean():+.2f}%"
        )

        print(
            f"Average MAE:         "
            f"{df['mae'].mean():+.2f}%"
        )


# ============================================================
# GROUP SUMMARY
# ============================================================

def print_group_summary(df, group_column):

    if df.empty:
        return

    result = df.groupby(
        group_column,
        observed=False
    ).agg(
        trades=("signal_id", "count"),
        invested=("invested", "sum"),
        pnl=("realized_pnl", "sum"),
        avg_pnl=("realized_pnl", "mean"),
        avg_return=("realized_pct", "mean"),
        winners=("winner", "sum"),
        avg_mfe=("mfe", "mean"),
        avg_mae=("mae", "mean"),
    )

    result["win_rate"] = (
        result["winners"]
        / result["trades"]
        * 100.0
    )

    result = result[
        [
            "trades",
            "invested",
            "pnl",
            "avg_pnl",
            "avg_return",
            "win_rate",
            "avg_mfe",
            "avg_mae",
        ]
    ]

    print(
        result.to_string(
            float_format=lambda x: f"{x:.4f}"
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print("S6 ENTRY GATE CALIBRATION")
    print("=" * 80)

    # --------------------------------------------------------
    # DATASET IDS
    # --------------------------------------------------------

    train_ids = load_ids(
        TRAIN_CSV
    )

    val_ids = load_ids(
        VAL_CSV
    )

    test_ids = load_ids(
        TEST_CSV
    )

    print()
    print("DATASET SIGNAL COUNTS")
    print("-" * 80)

    print(
        f"Train:                 {len(train_ids)}"
    )

    print(
        f"Validation:            {len(val_ids)}"
    )

    print(
        f"Test:                  {len(test_ids)}"
    )


    # --------------------------------------------------------
    # LOAD TRADES
    # --------------------------------------------------------

    print()
    print("Loading S6 trades...")

    trades = load_s6_trades()

    print(
        f"Closed S6 trades:      {len(trades)}"
    )

    if trades.empty:

        print(
            "ERROR: No closed S6 trades found."
        )

        return


    # --------------------------------------------------------
    # DATASET LABEL
    # --------------------------------------------------------

    trades["dataset"] = trades[
        "signal_id"
    ].apply(
        lambda x: classify_dataset(
            x,
            train_ids,
            val_ids,
            test_ids
        )
    )


    print()
    print("S6 TRADES BY DATASET")
    print("-" * 80)

    print(
        trades["dataset"]
        .value_counts()
        .to_string()
    )


    # --------------------------------------------------------
    # SNAPSHOTS
    # --------------------------------------------------------

    signal_ids = set(
        trades["signal_id"]
        .astype(str)
    )

    print()
    print(
        f"Loading snapshots for "
        f"{len(signal_ids)} traded signals..."
    )

    snapshots = load_relevant_snapshots(
        signal_ids
    )

    print(
        f"Relevant snapshots loaded: "
        f"{len(snapshots)}"
    )

    trades = attach_entry_snapshots(
        trades,
        snapshots
    )


    # --------------------------------------------------------
    # ACTUAL S6 STRATEGY
    # --------------------------------------------------------

    strategy = Strategy_S6_Moonshot_Ladder()

    print()
    print(
        "Calculating ACTUAL S6 compute_entry_quality()..."
    )

    trades["Q"] = trades.apply(
        lambda row: calculate_q(
            row,
            strategy
        ),
        axis=1
    )


    # --------------------------------------------------------
    # WINNER FLAG
    # --------------------------------------------------------

    trades["winner"] = (
        trades["realized_pnl"] > 0
    ).astype(int)


    # --------------------------------------------------------
    # Q TIERS
    # --------------------------------------------------------

    trades["Q_tier"] = pd.cut(
        trades["Q"],
        bins=[
            -np.inf,
            0.35,
            0.60,
            0.80,
            np.inf
        ],
        labels=[
            "<0.35",
            "0.35-0.60",
            "0.60-0.80",
            ">=0.80"
        ]
    )


    # --------------------------------------------------------
    # FINAL SCORE BANDS
    # --------------------------------------------------------

    trades["score_band"] = pd.cut(
        trades["final_score"],
        bins=[
            -np.inf,
            59,
            64,
            69,
            np.inf
        ],
        labels=[
            "<60",
            "60-64",
            "65-69",
            ">=70"
        ]
    )


    # ========================================================
    # TRAIN + VALIDATION
    # ========================================================

    calibration = trades[
        trades["dataset"].isin(
            ["TRAIN", "VALIDATION"]
        )
    ].copy()

    summarize(
        calibration,
        "TRAIN + VALIDATION — CALIBRATION DATA"
    )


    # ========================================================
    # Q TIER PERFORMANCE
    # ========================================================

    print()
    print("=" * 80)
    print("Q TIER PERFORMANCE")
    print("=" * 80)

    print_group_summary(
        calibration,
        "Q_tier"
    )


    # ========================================================
    # FINAL SCORE PERFORMANCE
    # ========================================================

    print()
    print("=" * 80)
    print("FINAL SCORE PERFORMANCE")
    print("=" * 80)

    print_group_summary(
        calibration,
        "score_band"
    )


    # ========================================================
    # Q CORRELATION
    # ========================================================

    print()
    print("=" * 80)
    print("Q vs REALIZED OUTCOME")
    print("=" * 80)

    corr_columns = [
        "Q",
        "final_score",
        "gt_score",
        "signal_market_cap",
        "liquidity",
        "buys",
        "sells",
        "realized_pnl",
        "realized_pct",
        "mfe",
        "mae",
    ]

    corr = (
        calibration[corr_columns]
        .corr(numeric_only=True)
        ["realized_pnl"]
        .drop("realized_pnl")
        .sort_values(
            key=lambda x: abs(x),
            ascending=False
        )
    )

    print(
        corr.to_string(
            float_format=lambda x: f"{x:.5f}"
        )
    )


    # ========================================================
    # WINNERS VS LOSERS
    # ========================================================

    print()
    print("=" * 80)
    print("Q DISTRIBUTION — WINNERS VS LOSERS")
    print("=" * 80)

    winner_summary = calibration.groupby(
        "winner",
        observed=False
    ).agg(
        trades=("signal_id", "count"),
        avg_Q=("Q", "mean"),
        median_Q=("Q", "median"),
        avg_final_score=("final_score", "mean"),
        avg_gt_score=("gt_score", "mean"),
        avg_pnl=("realized_pnl", "mean"),
        avg_return=("realized_pct", "mean"),
        avg_mfe=("mfe", "mean"),
        avg_mae=("mae", "mean"),
    )

    winner_summary.index = [
        "LOSERS",
        "WINNERS"
    ][:len(winner_summary)]

    print(
        winner_summary.to_string(
            float_format=lambda x: f"{x:.4f}"
        )
    )


    # ========================================================
    # EXIT REASONS
    # ========================================================

    print()
    print("=" * 80)
    print("EXIT REASONS — CALIBRATION DATA")
    print("=" * 80)

    exit_summary = calibration.groupby(
        "exit_reason",
        observed=False
    ).agg(
        trades=("signal_id", "count"),
        pnl=("realized_pnl", "sum"),
        avg_pnl=("realized_pnl", "mean"),
        avg_return=("realized_pct", "mean"),
    )

    print(
        exit_summary.sort_values(
            "trades",
            ascending=False
        ).to_string(
            float_format=lambda x: f"{x:.4f}"
        )
    )


    # ========================================================
    # FINAL TEST — REPORT ONLY
    # ========================================================

    test = trades[
        trades["dataset"] == "TEST"
    ].copy()

    summarize(
        test,
        "FINAL TEST — REPORT ONLY / NO TUNING"
    )


    print()
    print("=" * 80)
    print("FINAL TEST Q TIER PERFORMANCE")
    print("=" * 80)

    print_group_summary(
        test,
        "Q_tier"
    )


    print()
    print("=" * 80)
    print("FINAL TEST SCORE BAND PERFORMANCE")
    print("=" * 80)

    print_group_summary(
        test,
        "score_band"
    )


    # ========================================================
    # FINAL TEST TRADE TABLE
    # ========================================================

    print()
    print("=" * 80)
    print("FINAL TEST TRADES")
    print("=" * 80)

    columns = [
        "signal_id",
        "symbol",
        "decision",
        "final_score",
        "gt_score",
        "Q",
        "Q_tier",
        "invested",
        "realized_pnl",
        "realized_pct",
        "mfe",
        "mae",
        "exit_reason",
    ]

    available_columns = [
        c for c in columns
        if c in test.columns
    ]

    print(
        test[available_columns]
        .sort_values("Q")
        .to_string(index=False)
    )


    # ========================================================
    # SAVE
    # ========================================================

    trades.to_csv(
        OUTPUT_CSV,
        index=False
    )

    print()
    print("=" * 80)
    print("CALIBRATION COMPLETE")
    print("=" * 80)

    print(
        f"Output: {OUTPUT_CSV}"
    )


if __name__ == "__main__":
    main()
