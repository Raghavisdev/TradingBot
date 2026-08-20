"""
S6 Forward Sizing Tracker
-------------------------
Paper-only diagnostic tool.

Purpose:
    Compare the economics of different S6 position-sizing schemes
    using CLOSED S6_Moonshot_Ladder trades.

IMPORTANT:
    - Does NOT modify S6 strategy code.
    - Does NOT modify the database.
    - Does NOT create or close trades.
    - Does NOT change the live/paper S6 portfolio.
    - Uses actual realized S6 return percentages.
"""

import sqlite3
from pathlib import Path

import pandas as pd


DB = "database/trading.db"
OUTPUT_DIR = Path("analytics/s7_models")

OUTPUT_CSV = OUTPUT_DIR / "S6_SIZING_FORWARD_TRACKER.csv"
OUTPUT_REPORT = OUTPUT_DIR / "S6_SIZING_FORWARD_TRACKER.txt"

STRATEGY_ID = "S6_Moonshot_Ladder"


def q_from_signal(row):
    """
    Reproduce the current S6 entry-quality Q calculation
    using the same five components visible in strategies.py.

    We deliberately keep this diagnostic-only.
    """

    # ---------------------------------------------------------
    # 1. Buy / sell ratio — 30%
    # ---------------------------------------------------------

    buys = row["buys"]
    sells = row["sells"]

    if pd.notna(buys) and pd.notna(sells) and float(sells) > 0:
        bs_ratio = float(buys) / float(sells)
    elif pd.notna(row["buy_sell_ratio"]):
        bs_ratio = float(row["buy_sell_ratio"])
    else:
        bs_ratio = 1.0

    if bs_ratio < 1.0:
        q_bs = 0.0
    elif bs_ratio < 1.2:
        q_bs = 0.5
    elif bs_ratio < 1.5:
        q_bs = 0.8
    else:
        q_bs = 1.0

    # ---------------------------------------------------------
    # 2. Liquidity — 25%
    # ---------------------------------------------------------

    liq = float(row["liquidity"] or 0.0)

    if liq <= 0:
        q_liq = 0.0
    elif liq < 1000:
        q_liq = 0.2
    elif liq < 10000:
        q_liq = 0.6
    else:
        q_liq = 1.0

    # ---------------------------------------------------------
    # 3. Market cap — 15%
    # ---------------------------------------------------------

    mc = float(row["signal_market_cap"] or 0.0)

    if mc <= 0:
        q_mc = 0.0

    elif 35000 <= mc <= 44000:
        q_mc = 1.0

    elif 25000 <= mc < 35000:
        q_mc = 0.6 + 0.4 * ((mc - 25000) / 10000)

    elif 44000 < mc <= 60000:
        q_mc = 1.0 - 0.4 * ((mc - 44000) / 16000)

    elif 15000 <= mc < 25000:
        q_mc = 0.3 + 0.3 * ((mc - 15000) / 10000)

    elif 60000 < mc <= 100000:
        q_mc = 0.6 - 0.4 * ((mc - 60000) / 40000)

    else:
        q_mc = 0.2

    # ---------------------------------------------------------
    # 4. GT score — 15%
    # ---------------------------------------------------------

    gt = float(row["gt_score"] or 0.0)

    if gt >= 3:
        q_gt = 1.0
    elif gt >= 2:
        q_gt = 0.6
    elif gt >= 1:
        q_gt = 0.2
    else:
        q_gt = 0.0

    # ---------------------------------------------------------
    # 5. Final score — 15%
    # ---------------------------------------------------------

    fs = float(row["final_score"] or 0.0)

    if fs >= 70:
        q_fs = 1.0
    elif fs >= 65:
        q_fs = 0.7
    elif fs >= 60:
        q_fs = 0.3
    else:
        q_fs = 0.0

    Q = (
        0.30 * q_bs
        + 0.25 * q_liq
        + 0.15 * q_mc
        + 0.15 * q_gt
        + 0.15 * q_fs
    )

    return min(max(Q, 0.0), 1.0)


def current_s6_size(q):
    """Current S6 sizing tiers."""

    if q < 0.35:
        return 2.00
    elif q < 0.60:
        return 5.00
    elif q < 0.80:
        return 9.00
    else:
        return 14.00


def conservative_size(q):
    """Experimental conservative high-Q sizing."""

    if q < 0.35:
        return 2.00
    elif q < 0.60:
        return 5.00
    elif q < 0.80:
        return 7.00
    else:
        return 7.00


def flat_size(q):
    """Experimental flat sizing."""

    return 5.00


def load_closed_s6_trades():
    con = sqlite3.connect(DB)

    query = """
    SELECT
        p.id,
        p.trade_id,
        p.signal_id,
        p.strategy_version,
        p.entry_time,
        p.entry_price,
        p.entry_market_cap,
        p.invested,
        p.exit_time,
        p.exit_price,
        p.exit_market_cap,
        p.exit_reason,
        p.realized_pnl,
        p.realized_pct,
        p.mfe,
        p.mae,
        p.peak_multiple,

        s.timestamp,
        s.symbol,
        s.name,
        s.signal_market_cap,
        s.signal_price,
        s.gt_score,
        s.decision,
        s.final_score,

        sn.liquidity,
        sn.volume,
        sn.buys,
        sn.sells,

        i.buy_sell_ratio,
        i.mc_velocity,
        i.holder_velocity,
        i.volume_velocity,
        i.buy_velocity,
        i.liquidity_change,
        i.mc_acceleration,
        i.volume_acceleration,
        i.sentiment_strength

    FROM paper_lab_trades p

    LEFT JOIN signals s
        ON s.signal_id = p.signal_id

    LEFT JOIN (
        SELECT
            signal_id,
            liquidity,
            volume,
            buys,
            sells
        FROM snapshots
        WHERE id IN (
            SELECT MIN(id)
            FROM snapshots
            GROUP BY signal_id
        )
    ) sn
        ON sn.signal_id = p.signal_id

    LEFT JOIN (
        SELECT
            signal_id,
            buy_sell_ratio,
            mc_velocity,
            holder_velocity,
            volume_velocity,
            buy_velocity,
            liquidity_change,
            mc_acceleration,
            volume_acceleration,
            sentiment_strength
        FROM intelligence
        WHERE id IN (
            SELECT MIN(id)
            FROM intelligence
            GROUP BY signal_id
        )
    ) i
        ON i.signal_id = p.signal_id

    WHERE p.strategy_id = ?
      AND p.status = 'CLOSED'

    ORDER BY p.exit_time ASC
    """

    df = pd.read_sql_query(
        query,
        con,
        params=[STRATEGY_ID],
    )

    con.close()

    return df


def build_tracker(df):
    if df.empty:
        return df

    df = df.copy()

    # ---------------------------------------------------------
    # Clean numeric fields
    # ---------------------------------------------------------

    numeric_cols = [
        "realized_pct",
        "realized_pnl",
        "invested",
        "mfe",
        "mae",
        "peak_multiple",
        "final_score",
        "gt_score",
        "signal_market_cap",
        "liquidity",
        "volume",
        "buys",
        "sells",
        "buy_sell_ratio",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

    # ---------------------------------------------------------
    # Fill missing diagnostic fields
    # ---------------------------------------------------------

    for col in [
        "buys",
        "sells",
        "liquidity",
        "signal_market_cap",
        "gt_score",
        "final_score",
    ]:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    # ---------------------------------------------------------
    # Calculate Q
    # ---------------------------------------------------------

    df["Q"] = df.apply(q_from_signal, axis=1)

    # ---------------------------------------------------------
    # Current and experimental sizes
    # ---------------------------------------------------------

    df["current_s6_size"] = df["Q"].apply(current_s6_size)
    df["conservative_size"] = df["Q"].apply(conservative_size)
    df["flat_size"] = df["Q"].apply(flat_size)

    # ---------------------------------------------------------
    # IMPORTANT:
    #
    # realized_pct is the actual return produced by the
    # S6 Moonshot Ladder exit mechanics.
    #
    # Scale that same return to each hypothetical investment.
    # ---------------------------------------------------------

    return_fraction = df["realized_pct"] / 100.0

    df["current_hyp_pnl"] = (
        return_fraction * df["current_s6_size"]
    )

    df["conservative_hyp_pnl"] = (
        return_fraction * df["conservative_size"]
    )

    df["flat_hyp_pnl"] = (
        return_fraction * df["flat_size"]
    )

    # Actual S6 accounting
    df["actual_pnl"] = df["realized_pnl"]

    # ---------------------------------------------------------
    # Differences vs actual
    # ---------------------------------------------------------

    df["conservative_minus_current"] = (
        df["conservative_hyp_pnl"]
        - df["current_hyp_pnl"]
    )

    df["flat_minus_current"] = (
        df["flat_hyp_pnl"]
        - df["current_hyp_pnl"]
    )

    return df


def summary(df, pnl_col, size_col):
    if df.empty:
        return {
            "trades": 0,
            "invested": 0.0,
            "pnl": 0.0,
            "roi": 0.0,
            "win_rate": 0.0,
        }

    invested = df[size_col].sum()
    pnl = df[pnl_col].sum()

    roi = (
        pnl / invested * 100.0
        if invested > 0
        else 0.0
    )

    win_rate = (
        (df[pnl_col] > 0).mean() * 100.0
    )

    return {
        "trades": len(df),
        "invested": invested,
        "pnl": pnl,
        "roi": roi,
        "win_rate": win_rate,
    }


def print_report(df):
    print("=" * 78)
    print("S6 FORWARD SIZING TRACKER")
    print("=" * 78)

    print()
    print("CLOSED S6 TRADES")
    print("-" * 78)
    print(f"Trades: {len(df)}")

    if df.empty:
        print("No closed S6 trades found.")
        return

    # ---------------------------------------------------------
    # Actual S6
    # ---------------------------------------------------------

    actual_pnl = df["actual_pnl"].sum()
    actual_invested = df["invested"].sum()

    actual_roi = (
        actual_pnl / actual_invested * 100.0
        if actual_invested > 0
        else 0.0
    )

    actual_win = (
        (df["actual_pnl"] > 0).mean() * 100.0
    )

    print()
    print("ACTUAL S6")
    print("-" * 78)
    print(f"Invested:       ${actual_invested:.4f}")
    print(f"Realized P&L:   ${actual_pnl:+.4f}")
    print(f"ROI:             {actual_roi:+.4f}%")
    print(f"Win rate:        {actual_win:.2f}%")

    # ---------------------------------------------------------
    # Current Q sizing
    # ---------------------------------------------------------

    cur = summary(
        df,
        "current_hyp_pnl",
        "current_s6_size",
    )

    con = summary(
        df,
        "conservative_hyp_pnl",
        "conservative_size",
    )

    flat = summary(
        df,
        "flat_hyp_pnl",
        "flat_size",
    )

    print()
    print("HYPOTHETICAL SIZING COMPARISON")
    print("-" * 78)

    print(
        f"{'Strategy':<22}"
        f"{'Invested':>12}"
        f"{'P&L':>12}"
        f"{'ROI':>12}"
        f"{'Win%':>10}"
    )

    print("-" * 78)

    print(
        f"{'Current Q tiers':<22}"
        f"${cur['invested']:>10.2f}"
        f"${cur['pnl']:>+10.2f}"
        f"{cur['roi']:>+10.2f}%"
        f"{cur['win_rate']:>9.2f}%"
    )

    print(
        f"{'Conservative':<22}"
        f"${con['invested']:>10.2f}"
        f"${con['pnl']:>+10.2f}"
        f"{con['roi']:>+10.2f}%"
        f"{con['win_rate']:>9.2f}%"
    )

    print(
        f"{'Flat $5':<22}"
        f"${flat['invested']:>10.2f}"
        f"${flat['pnl']:>+10.2f}"
        f"{flat['roi']:>+10.2f}%"
        f"{flat['win_rate']:>9.2f}%"
    )

    print()
    print("Q-TIER BREAKDOWN")
    print("-" * 78)

    bins = [
        (-1, 0.35, "<0.35"),
        (0.35, 0.60, "0.35-0.60"),
        (0.60, 0.80, "0.60-0.80"),
        (0.80, 2, ">=0.80"),
    ]

    for low, high, label in bins:

        if label == ">=0.80":
            part = df[
                (df["Q"] >= low)
                & (df["Q"] < high)
            ]
        else:
            part = df[
                (df["Q"] >= low)
                & (df["Q"] < high)
            ]

        if part.empty:
            continue

        pnl = part["actual_pnl"].sum()
        invested = part["invested"].sum()
        win = (part["actual_pnl"] > 0).mean() * 100

        roi = (
            pnl / invested * 100
            if invested > 0
            else 0
        )

        print(
            f"{label:<12}"
            f" trades={len(part):>3}"
            f" invested=${invested:>8.2f}"
            f" pnl=${pnl:>+8.2f}"
            f" ROI={roi:>+7.2f}%"
            f" win={win:>6.2f}%"
        )

    print()
    print("NOTE")
    print("-" * 78)
    print(
        "Hypothetical P&Ls are calculated by scaling the actual "
        "S6 realized return percentage to alternative investment "
        "sizes. They do NOT change the S6 ledger."
    )


def save_outputs(df):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    with open(
        OUTPUT_REPORT,
        "w",
        encoding="utf-8",
    ) as f:

        f.write("=" * 78 + "\n")
        f.write("S6 FORWARD SIZING TRACKER\n")
        f.write("=" * 78 + "\n\n")

        f.write(
            f"Closed S6 trades: {len(df)}\n\n"
        )

        if not df.empty:

            actual_pnl = df["actual_pnl"].sum()
            actual_invested = df["invested"].sum()

            actual_roi = (
                actual_pnl / actual_invested * 100
                if actual_invested > 0
                else 0
            )

            f.write(
                f"Actual invested: ${actual_invested:.4f}\n"
            )
            f.write(
                f"Actual P&L: ${actual_pnl:+.4f}\n"
            )
            f.write(
                f"Actual ROI: {actual_roi:+.4f}%\n\n"
            )

            for name, pnl_col, size_col in [
                (
                    "Current Q tiers",
                    "current_hyp_pnl",
                    "current_s6_size",
                ),
                (
                    "Conservative",
                    "conservative_hyp_pnl",
                    "conservative_size",
                ),
                (
                    "Flat $5",
                    "flat_hyp_pnl",
                    "flat_size",
                ),
            ]:

                s = summary(
                    df,
                    pnl_col,
                    size_col,
                )

                f.write(
                    f"{name}\n"
                    f"  Invested: ${s['invested']:.4f}\n"
                    f"  P&L: ${s['pnl']:+.4f}\n"
                    f"  ROI: {s['roi']:+.4f}%\n"
                    f"  Win rate: {s['win_rate']:.2f}%\n\n"
                )

    print()
    print(f"CSV:    {OUTPUT_CSV}")
    print(f"Report: {OUTPUT_REPORT}")


def main():
    df = load_closed_s6_trades()

    if df.empty:
        print_report(df)
        return

    df = build_tracker(df)

    print_report(df)

    save_outputs(df)


if __name__ == "__main__":
    main()
