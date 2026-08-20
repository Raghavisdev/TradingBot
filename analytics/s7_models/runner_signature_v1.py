import sqlite3
import numpy as np
import pandas as pd

DB = "database/trading.db"

con = sqlite3.connect(DB)

print("=" * 90)
print("S7 RUNNER SIGNATURE ANALYSIS V1")
print("=" * 90)

# ============================================================
# Build one T0 record for every historical S6 trade
# ============================================================

query = """
WITH first_snap AS (
    SELECT
        signal_id,
        MIN(CAST(timestamp AS REAL)) AS t0
    FROM snapshots
    GROUP BY signal_id
)
SELECT
    t.signal_id,
    t.symbol,
    t.invested,
    t.realized_pnl,
    t.realized_pct,
    t.mfe,
    t.mae,

    s.gt_score,
    s.final_score,
    s.signal_market_cap,

    x.market_cap,
    x.liquidity,
    x.volume,
    x.buys,
    x.sells,
    x.holders,

    CASE
        WHEN x.sells > 0
        THEN CAST(x.buys AS REAL) / x.sells
        ELSE NULL
    END AS bs_ratio,

    x.market_health

FROM paper_lab_trades t

JOIN signals s
    ON s.signal_id = t.signal_id

JOIN first_snap f
    ON f.signal_id = t.signal_id

JOIN snapshots x
    ON x.signal_id = t.signal_id
    AND CAST(x.timestamp AS REAL) = f.t0

WHERE t.strategy_id = 'S6_Moonshot_Ladder'
  AND t.status = 'CLOSED'
"""

df = pd.read_sql_query(query, con)

print()
print("Historical S6 records:", len(df))

# ============================================================
# Runner labels
# ============================================================

df["runner_50"] = (df["mfe"] >= 50).astype(int)
df["runner_100"] = (df["mfe"] >= 100).astype(int)
df["runner_200"] = (df["mfe"] >= 200).astype(int)

print()
print("=" * 90)
print("RUNNER POPULATION")
print("=" * 90)

print(
    "MFE >= 50% :",
    int(df["runner_50"].sum())
)

print(
    "MFE >= 100%:",
    int(df["runner_100"].sum())
)

print(
    "MFE >= 200%:",
    int(df["runner_200"].sum())
)

# ============================================================
# Candidate T0 features
# ============================================================

features = [
    "gt_score",
    "final_score",
    "signal_market_cap",
    "market_cap",
    "liquidity",
    "volume",
    "buys",
    "sells",
    "holders",
    "bs_ratio",
]

# ============================================================
# Compare runners vs non-runners
# ============================================================

def compare(label):

    runner = df[df[label] == 1]
    nonrunner = df[df[label] == 0]

    print()
    print("=" * 90)
    print(f"{label.upper()} — T0 FEATURE COMPARISON")
    print("=" * 90)

    print(
        f"Runner N={len(runner)} | "
        f"Non-runner N={len(nonrunner)}"
    )

    rows = []

    for feature in features:

        a = pd.to_numeric(
            runner[feature],
            errors="coerce"
        ).dropna()

        b = pd.to_numeric(
            nonrunner[feature],
            errors="coerce"
        ).dropna()

        if len(a) == 0 or len(b) == 0:
            continue

        rows.append({
            "feature": feature,
            "runner_mean": a.mean(),
            "runner_median": a.median(),
            "nonrunner_mean": b.mean(),
            "nonrunner_median": b.median(),
            "difference": a.mean() - b.mean(),
        })

    out = pd.DataFrame(rows)

    if not out.empty:
        print(
            out.to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}"
            )
        )


compare("runner_50")
compare("runner_100")
compare("runner_200")

# ============================================================
# Quantile analysis
# ============================================================

print()
print("=" * 90)
print("TOP T0 FEATURE ASSOCIATIONS WITH MFE")
print("=" * 90)

for feature in features:

    x = pd.to_numeric(
        df[feature],
        errors="coerce"
    )

    y = pd.to_numeric(
        df["mfe"],
        errors="coerce"
    )

    valid = x.notna() & y.notna()

    if valid.sum() < 10:
        continue

    corr = x[valid].corr(y[valid], method="spearman")

    print(
        f"{feature:20s} "
        f"Spearman={corr:+.4f}"
    )

# ============================================================
# Simple percentile buckets
# ============================================================

print()
print("=" * 90)
print("FEATURE BUCKETS — RUNNER RATE")
print("=" * 90)

for feature in [
    "market_cap",
    "volume",
    "liquidity",
    "bs_ratio",
    "final_score",
    "holders",
]:

    x = pd.to_numeric(
        df[feature],
        errors="coerce"
    )

    valid = x.notna()

    if valid.sum() < 20:
        continue

    try:
        buckets = pd.qcut(
            x[valid],
            q=4,
            duplicates="drop"
        )

        tmp = pd.DataFrame({
            "bucket": buckets,
            "runner": df.loc[
                valid,
                "runner_100"
            ].values
        })

        grouped = tmp.groupby(
            "bucket",
            observed=True
        )["runner"].agg(
            ["count", "mean"]
        )

        print()
        print(feature)

        for idx, row in grouped.iterrows():
            print(
                f"  {str(idx):25s} "
                f"N={int(row['count']):3d} "
                f"100x-runner-rate={row['mean']*100:6.2f}%"
            )

    except Exception:
        pass

# ============================================================
# Strong runner profiles
# ============================================================

print()
print("=" * 90)
print("STRONG RUNNERS — T0 SNAPSHOT")
print("=" * 90)

cols = [
    "symbol",
    "mfe",
    "realized_pnl",
    "final_score",
    "signal_market_cap",
    "market_cap",
    "liquidity",
    "volume",
    "buys",
    "sells",
    "bs_ratio",
    "holders",
]

print(
    df.sort_values(
        "mfe",
        ascending=False
    )[cols].head(20).to_string(
        index=False
    )
)

# ============================================================
# Save
# ============================================================

out = "analytics/s7_models/runner_signature_v1.csv"

df.to_csv(
    out,
    index=False
)

print()
print("=" * 90)
print("DONE")
print("=" * 90)
print("Saved:", out)

