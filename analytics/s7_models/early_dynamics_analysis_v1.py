import sqlite3
import numpy as np
import pandas as pd

DB = "database/trading.db"

con = sqlite3.connect(DB)

print("=" * 90)
print("S7 EARLY DYNAMICS RUNNER ANALYSIS V1")
print("=" * 90)

# ============================================================
# 1. HISTORICAL S6 TRADES
# ============================================================

trades = pd.read_sql_query(
    """
    SELECT
        signal_id,
        symbol,
        invested,
        realized_pnl,
        mfe,
        mae
    FROM paper_lab_trades
    WHERE strategy_id = 'S6_Moonshot_Ladder'
      AND status = 'CLOSED'
    """,
    con,
)

trades["signal_id"] = trades["signal_id"].astype(str)

print()
print("Historical S6 trades:", len(trades))

# ============================================================
# 2. GET T0 + FUTURE SNAPSHOTS
# ============================================================

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
        CAST(holders AS REAL) AS holders
    FROM snapshots
    WHERE price > 0
    ORDER BY signal_id, timestamp
    """,
    con,
)

snapshots["signal_id"] = snapshots["signal_id"].astype(str)

trade_ids = set(trades["signal_id"])

snapshots = snapshots[
    snapshots["signal_id"].isin(trade_ids)
].copy()

# ============================================================
# 3. CALCULATE EARLY DYNAMICS
# ============================================================

records = []

for signal_id, g in snapshots.groupby("signal_id"):

    g = g.sort_values("timestamp").reset_index(drop=True)

    if len(g) < 2:
        continue

    t0 = g.iloc[0]

    p0 = float(t0["price"] or 0)
    mc0 = float(t0["market_cap"] or 0)
    liq0 = float(t0["liquidity"] or 0)
    vol0 = float(t0["volume"] or 0)
    buys0 = float(t0["buys"] or 0)
    sells0 = float(t0["sells"] or 0)

    if p0 <= 0:
        continue

    if sells0 > 0:
        bs0 = buys0 / sells0
    else:
        bs0 = buys0 if buys0 > 0 else 1.0

    row = {
        "signal_id": signal_id,
        "t0_price": p0,
        "t0_mc": mc0,
        "t0_liq": liq0,
        "t0_vol": vol0,
        "t0_bs": bs0,
    }

    # --------------------------------------------------------
    # Examine early windows.
    #
    # We use snapshot counts rather than assuming timestamps
    # have a fixed interval.
    # --------------------------------------------------------

    windows = {
        "s1": 1,
        "s3": 3,
        "s5": 5,
        "s10": 10,
    }

    for name, idx in windows.items():

        if len(g) <= idx:
            continue

        x = g.iloc[idx]

        price = float(x["price"] or 0)
        mc = float(x["market_cap"] or 0)
        liq = float(x["liquidity"] or 0)
        vol = float(x["volume"] or 0)
        buys = float(x["buys"] or 0)
        sells = float(x["sells"] or 0)

        if price > 0:
            row[f"{name}_price_pct"] = (
                (price / p0) - 1.0
            ) * 100.0

        if mc0 > 0 and mc > 0:
            row[f"{name}_mc_pct"] = (
                (mc / mc0) - 1.0
            ) * 100.0

        if liq0 > 0 and liq > 0:
            row[f"{name}_liq_pct"] = (
                (liq / liq0) - 1.0
            ) * 100.0

        if vol0 > 0:
            row[f"{name}_vol_ratio"] = (
                vol / vol0
            )

        if sells > 0:
            row[f"{name}_bs"] = buys / sells
        elif buys > 0:
            row[f"{name}_bs"] = min(buys, 3.0)

        if bs0 > 0 and f"{name}_bs" in row:
            row[f"{name}_bs_delta"] = (
                row[f"{name}_bs"] - bs0
            )

    records.append(row)

df = pd.DataFrame(records)

df = df.merge(
    trades[
        [
            "signal_id",
            "symbol",
            "realized_pnl",
            "mfe",
            "mae",
        ]
    ],
    on="signal_id",
    how="inner",
)

print()
print("Usable trades:", len(df))

# ============================================================
# 4. RUNNER LABELS
# ============================================================

df["runner_50"] = df["mfe"] >= 50
df["runner_100"] = df["mfe"] >= 100
df["runner_200"] = df["mfe"] >= 200

print()
print("=" * 90)
print("RUNNER POPULATION")
print("=" * 90)

print("MFE >= 50% :", int(df["runner_50"].sum()))
print("MFE >=100% :", int(df["runner_100"].sum()))
print("MFE >=200% :", int(df["runner_200"].sum()))

# ============================================================
# 5. FEATURE COMPARISON
# ============================================================

features = [
    "s1_price_pct",
    "s3_price_pct",
    "s5_price_pct",
    "s10_price_pct",

    "s1_mc_pct",
    "s3_mc_pct",
    "s5_mc_pct",
    "s10_mc_pct",

    "s1_liq_pct",
    "s3_liq_pct",
    "s5_liq_pct",
    "s10_liq_pct",

    "s1_vol_ratio",
    "s3_vol_ratio",
    "s5_vol_ratio",
    "s10_vol_ratio",

    "s1_bs_delta",
    "s3_bs_delta",
    "s5_bs_delta",
    "s10_bs_delta",
]

def compare(label_col):

    print()
    print("=" * 90)
    print(label_col.upper(), "— EARLY DYNAMICS")
    print("=" * 90)

    runner = df[df[label_col]]
    nonrunner = df[~df[label_col]]

    print(
        "Runner:",
        len(runner),
        "| Non-runner:",
        len(nonrunner),
    )

    results = []

    for feature in features:

        if feature not in df.columns:
            continue

        a = runner[feature].dropna()
        b = nonrunner[feature].dropna()

        if len(a) == 0 or len(b) == 0:
            continue

        results.append(
            {
                "feature": feature,
                "runner_mean": a.mean(),
                "runner_median": a.median(),
                "nonrunner_mean": b.mean(),
                "nonrunner_median": b.median(),
                "difference": a.mean() - b.mean(),
            }
        )

    out = pd.DataFrame(results)

    if not out.empty:
        out["abs_difference"] = out["difference"].abs()

        print(
            out.sort_values(
                "abs_difference",
                ascending=False,
            ).drop(
                columns=["abs_difference"]
            ).to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}",
            )
        )


compare("runner_50")
compare("runner_100")
compare("runner_200")

# ============================================================
# 6. SPEARMAN CORRELATIONS
# ============================================================

print()
print("=" * 90)
print("EARLY FEATURE CORRELATION WITH MFE")
print("=" * 90)

corrs = []

for feature in features:

    if feature not in df.columns:
        continue

    temp = df[
        [feature, "mfe"]
    ].dropna()

    if len(temp) < 10:
        continue

    corr = temp[feature].corr(
        temp["mfe"],
        method="spearman",
    )

    corrs.append(
        {
            "feature": feature,
            "spearman": corr,
            "N": len(temp),
        }
    )

corr_df = pd.DataFrame(corrs)

if not corr_df.empty:

    print(
        corr_df.sort_values(
            "spearman",
            key=lambda x: x.abs(),
            ascending=False,
        ).to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

# ============================================================
# 7. EARLY MOMENTUM GATES
# ============================================================

print()
print("=" * 90)
print("EARLY MOMENTUM GATES")
print("=" * 90)

gates = {
    "S3 price >= +5%": (
        "s3_price_pct",
        5,
        ">=",
    ),
    "S3 price >= +10%": (
        "s3_price_pct",
        10,
        ">=",
    ),
    "S5 price >= +5%": (
        "s5_price_pct",
        5,
        ">=",
    ),
    "S5 price >= +10%": (
        "s5_price_pct",
        10,
        ">=",
    ),
    "S5 price >= +20%": (
        "s5_price_pct",
        20,
        ">=",
    ),
    "S5 volume ratio >= 1.5": (
        "s5_vol_ratio",
        1.5,
        ">=",
    ),
    "S5 volume ratio >= 2": (
        "s5_vol_ratio",
        2,
        ">=",
    ),
    "S5 B/S delta >= +0.2": (
        "s5_bs_delta",
        0.2,
        ">=",
    ),
    "S5 B/S delta >= +0.5": (
        "s5_bs_delta",
        0.5,
        ">=",
    ),
}

for name, (feature, threshold, op) in gates.items():

    if feature not in df.columns:
        continue

    subset = df[
        df[feature] >= threshold
    ].copy()

    if len(subset) == 0:
        continue

    print()
    print(
        f"{name:<32}"
        f"N={len(subset):3d} "
        f"50x={subset.runner_50.mean()*100:6.2f}% "
        f"100x={subset.runner_100.mean()*100:6.2f}% "
        f"200x={subset.runner_200.mean()*100:6.2f}% "
        f"avgMFE={subset.mfe.mean():8.2f}% "
        f"P&L=${subset.realized_pnl.sum():+9.4f}"
    )

# ============================================================
# 8. EARLY PRICE × VOLUME INTERACTION
# ============================================================

print()
print("=" * 90)
print("EARLY PRICE × VOLUME INTERACTION")
print("=" * 90)

if "s5_price_pct" in df.columns and "s5_vol_ratio" in df.columns:

    conditions = [
        (
            "PRICE<5 / VOL<1.5",
            (df.s5_price_pct < 5)
            & (df.s5_vol_ratio < 1.5),
        ),
        (
            "PRICE<5 / VOL>=1.5",
            (df.s5_price_pct < 5)
            & (df.s5_vol_ratio >= 1.5),
        ),
        (
            "PRICE>=5 / VOL<1.5",
            (df.s5_price_pct >= 5)
            & (df.s5_vol_ratio < 1.5),
        ),
        (
            "PRICE>=5 / VOL>=1.5",
            (df.s5_price_pct >= 5)
            & (df.s5_vol_ratio >= 1.5),
        ),
        (
            "PRICE>=10 / VOL>=2",
            (df.s5_price_pct >= 10)
            & (df.s5_vol_ratio >= 2),
        ),
    ]

    for name, mask in conditions:

        x = df[mask]

        if len(x) == 0:
            continue

        print(
            f"{name:<30}"
            f"N={len(x):3d} "
            f"50x={x.runner_50.mean()*100:6.2f}% "
            f"100x={x.runner_100.mean()*100:6.2f}% "
            f"200x={x.runner_200.mean()*100:6.2f}% "
            f"avgMFE={x.mfe.mean():8.2f}% "
            f"P&L=${x.realized_pnl.sum():+9.4f}"
        )

# ============================================================
# 9. SAVE
# ============================================================

out_path = (
    "analytics/s7_models/"
    "early_dynamics_analysis_v1.csv"
)

df.to_csv(
    out_path,
    index=False,
)

print()
print("=" * 90)
print("DONE")
print("=" * 90)
print("Saved:", out_path)

print()
print(
    "IMPORTANT: This is discovery only."
)
print(
    "Do NOT modify S6 or the live bot from this analysis alone."
)

con.close()
