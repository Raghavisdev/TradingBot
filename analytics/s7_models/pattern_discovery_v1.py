import sqlite3
import numpy as np
import pandas as pd

DB = "database/trading.db"

# ============================================================
# S7 PATTERN DISCOVERY V1
# ============================================================
#
# Purpose:
#   Discover patterns in ALL usable historical signals.
#
# We examine:
#   - final score
#   - GT score
#   - market cap
#   - liquidity
#   - volume
#   - buys / sells
#   - buy/sell ratio
#   - holders
#
# Outcomes:
#   - max return
#   - 2x
#   - 5x
#   - 10x
#   - rug
#
# IMPORTANT:
#   This is DISCOVERY ONLY.
#   It does NOT modify S6.
#   It does NOT change live trading.
#   It does NOT select the final strategy.
#
# ============================================================

con = sqlite3.connect(DB)

print("=" * 90)
print("S7 PATTERN DISCOVERY V1")
print("=" * 90)


# ============================================================
# 1. BUILD ONE T0 RECORD PER SIGNAL
# ============================================================

print()
print("Building T0 dataset...")

query = """
WITH ranked_snapshots AS (
    SELECT
        s.signal_id,
        s.timestamp AS signal_time,

        x.timestamp AS snapshot_time,
        x.market_cap,
        x.liquidity,
        x.volume,
        x.buys,
        x.sells,
        x.holders,

        ROW_NUMBER() OVER (
            PARTITION BY s.signal_id
            ORDER BY CAST(x.timestamp AS REAL)
        ) AS rn

    FROM signals s

    JOIN snapshots x
        ON x.signal_id = s.signal_id
       AND CAST(x.timestamp AS REAL)
           >= CAST(s.timestamp AS REAL)
)

SELECT
    s.signal_id,
    s.symbol,
    s.timestamp AS signal_time,

    s.gt_score,
    s.final_score,
    s.signal_market_cap,

    r.snapshot_time,
    r.market_cap,
    r.liquidity,
    r.volume,
    r.buys,
    r.sells,
    r.holders,

    o.max_return,
    o.min_return,
    o.rugged,
    o.returned_2x,
    o.returned_5x,
    o.returned_10x

FROM signals s

JOIN ranked_snapshots r
    ON r.signal_id = s.signal_id
   AND r.rn = 1

JOIN outcomes o
    ON CAST(o.signal_id AS TEXT)
       = CAST(s.signal_id AS TEXT)
"""

df = pd.read_sql_query(query, con)

print("Raw records:", len(df))


# ============================================================
# 2. NUMERIC CLEANUP
# ============================================================

numeric_cols = [
    "gt_score",
    "final_score",
    "signal_market_cap",
    "market_cap",
    "liquidity",
    "volume",
    "buys",
    "sells",
    "holders",
    "max_return",
    "min_return",
    "rugged",
    "returned_2x",
    "returned_5x",
    "returned_10x",
]

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )


# ============================================================
# 3. BUY / SELL RATIO
# ============================================================

df["bs_ratio"] = np.where(
    df["sells"] > 0,
    df["buys"] / df["sells"],
    np.where(
        df["buys"] > 0,
        np.minimum(df["buys"], 3.0),
        1.0
    )
)


# ============================================================
# 4. REMOVE INVALID RECORDS
# ============================================================

required = [
    "signal_id",
    "final_score",
    "max_return",
    "rugged",
    "returned_2x",
]

before = len(df)

df = df.dropna(
    subset=required
).copy()

df = df[
    np.isfinite(df["max_return"])
].copy()

print("Usable records:", len(df))
print("Removed:", before - len(df))


# ============================================================
# 5. BASIC OUTCOME SUMMARY
# ============================================================

print()
print("=" * 90)
print("BASELINE OUTCOMES")
print("=" * 90)

n = len(df)

rate_2x = df["returned_2x"].mean() * 100
rate_5x = df["returned_5x"].mean() * 100
rate_10x = df["returned_10x"].mean() * 100
rug_rate = df["rugged"].mean() * 100

print(f"N                  : {n}")
print(f"2x rate            : {rate_2x:.2f}%")
print(f"5x rate            : {rate_5x:.2f}%")
print(f"10x rate           : {rate_10x:.2f}%")
print(f"Rug rate           : {rug_rate:.2f}%")
print(f"Average max return : {df['max_return'].mean():.2f}%")
print(f"Median max return  : {df['max_return'].median():.2f}%")


# ============================================================
# 6. OUTCOME CORRELATION / FEATURE SUMMARY
# ============================================================

print()
print("=" * 90)
print("FEATURE DISTRIBUTIONS")
print("=" * 90)

features = [
    "gt_score",
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

for feature in features:

    if feature not in df.columns:
        continue

    x = df[feature].dropna()

    if len(x) == 0:
        continue

    print()
    print(feature)

    print(
        f"  mean   = {x.mean():.4f}"
    )

    print(
        f"  median = {x.median():.4f}"
    )

    print(
        f"  P25    = {x.quantile(.25):.4f}"
    )

    print(
        f"  P75    = {x.quantile(.75):.4f}"
    )


# ============================================================
# 7. FEATURE CORRELATIONS
# ============================================================

print()
print("=" * 90)
print("CORRELATION WITH OUTCOMES")
print("=" * 90)

targets = [
    "returned_2x",
    "returned_5x",
    "returned_10x",
    "rugged",
    "max_return",
]

corr_rows = []

for feature in features:

    for target in targets:

        tmp = df[
            [feature, target]
        ].dropna()

        if len(tmp) < 10:
            continue

        corr = tmp[feature].corr(
            tmp[target]
        )

        corr_rows.append({
            "feature": feature,
            "target": target,
            "correlation": corr,
        })

corr_df = pd.DataFrame(corr_rows)

if not corr_df.empty:

    for target in targets:

        print()
        print(f"--- {target} ---")

        part = (
            corr_df[
                corr_df["target"] == target
            ]
            .sort_values(
                "correlation",
                key=lambda x: x.abs(),
                ascending=False
            )
        )

        for _, row in part.head(10).iterrows():

            print(
                f"{row['feature']:22s} "
                f"{row['correlation']:+.4f}"
            )


# ============================================================
# 8. QUANTILE ANALYSIS
# ============================================================

print()
print("=" * 90)
print("QUANTILE ANALYSIS")
print("=" * 90)

for feature in features:

    if feature not in df.columns:
        continue

    try:

        tmp = df[
            [feature, "returned_2x",
             "returned_5x",
             "rugged",
             "max_return"]
        ].dropna()

        if len(tmp) < 30:
            continue

        tmp["bin"] = pd.qcut(
            tmp[feature],
            q=4,
            duplicates="drop"
        )

        grouped = (
            tmp.groupby(
                "bin",
                observed=True
            )
            .agg(
                N=("max_return", "size"),
                two_x=("returned_2x", "mean"),
                five_x=("returned_5x", "mean"),
                rug=("rugged", "mean"),
                avg_max=("max_return", "mean"),
            )
        )

        print()
        print("-" * 90)
        print(feature)

        for idx, row in grouped.iterrows():

            print(
                f"{str(idx):28s} "
                f"N={int(row['N']):4d} "
                f"2x={row['two_x']*100:6.2f}% "
                f"5x={row['five_x']*100:6.2f}% "
                f"rug={row['rug']*100:6.2f}% "
                f"avgMax={row['avg_max']:9.2f}%"
            )

    except Exception:
        pass


# ============================================================
# 9. CANDIDATE REGIME TESTER
# ============================================================

print()
print("=" * 90)
print("CANDIDATE ENTRY REGIMES")
print("=" * 90)


def evaluate_regime(
    name,
    mask
):

    sub = df[mask].copy()

    if len(sub) == 0:
        return

    n = len(sub)

    two = sub["returned_2x"].mean() * 100
    five = sub["returned_5x"].mean() * 100
    ten = sub["returned_10x"].mean() * 100
    rug = sub["rugged"].mean() * 100

    avg_max = sub["max_return"].mean()
    median_max = sub["max_return"].median()

    # Conservative discovery proxy.
    #
    # 5x = +4
    # 2x = +1
    # rug = -1
    #
    # This is NOT actual P&L.
    proxy = (
        np.where(
            sub["returned_5x"] == 1,
            4,
            np.where(
                sub["returned_2x"] == 1,
                1,
                np.where(
                    sub["rugged"] == 1,
                    -1,
                    0
                )
            )
        )
        .sum()
    )

    print(
        f"{name:45s} "
        f"N={n:4d} "
        f"2x={two:6.2f}% "
        f"5x={five:6.2f}% "
        f"10x={ten:6.2f}% "
        f"rug={rug:6.2f}% "
        f"avgMax={avg_max:9.2f}% "
        f"proxy={proxy:7.2f}"
    )


# ------------------------------------------------------------
# Single feature regimes
# ------------------------------------------------------------

evaluate_regime(
    "MC < 35k",
    df["market_cap"] < 35000
)

evaluate_regime(
    "MC 35-40k",
    (df["market_cap"] >= 35000)
    & (df["market_cap"] < 40000)
)

evaluate_regime(
    "MC 40-50k",
    (df["market_cap"] >= 40000)
    & (df["market_cap"] < 50000)
)

evaluate_regime(
    "MC >= 50k",
    df["market_cap"] >= 50000
)

evaluate_regime(
    "VOL < 20k",
    df["volume"] < 20000
)

evaluate_regime(
    "VOL 20-30k",
    (df["volume"] >= 20000)
    & (df["volume"] < 30000)
)

evaluate_regime(
    "VOL 30-50k",
    (df["volume"] >= 30000)
    & (df["volume"] < 50000)
)

evaluate_regime(
    "VOL >= 50k",
    df["volume"] >= 50000
)

evaluate_regime(
    "B/S < 1.0",
    df["bs_ratio"] < 1.0
)

evaluate_regime(
    "B/S 1.0-1.2",
    (df["bs_ratio"] >= 1.0)
    & (df["bs_ratio"] < 1.2)
)

evaluate_regime(
    "B/S 1.2-1.5",
    (df["bs_ratio"] >= 1.2)
    & (df["bs_ratio"] < 1.5)
)

evaluate_regime(
    "B/S >= 1.5",
    df["bs_ratio"] >= 1.5
)


# ============================================================
# 10. COMBINED REGIMES
# ============================================================

print()
print("=" * 90)
print("COMBINED REGIMES")
print("=" * 90)

regimes = [

    (
        "MC 35-40k + VOL 30k+",
        (df["market_cap"] >= 35000)
        & (df["market_cap"] < 40000)
        & (df["volume"] >= 30000)
    ),

    (
        "MC <40k + VOL 30k+",
        (df["market_cap"] < 40000)
        & (df["volume"] >= 30000)
    ),

    (
        "MC 35-40k + B/S >=1.2",
        (df["market_cap"] >= 35000)
        & (df["market_cap"] < 40000)
        & (df["bs_ratio"] >= 1.2)
    ),

    (
        "MC 35-40k + B/S >=1.3",
        (df["market_cap"] >= 35000)
        & (df["market_cap"] < 40000)
        & (df["bs_ratio"] >= 1.3)
    ),

    (
        "VOL >=30k + B/S >=1.2",
        (df["volume"] >= 30000)
        & (df["bs_ratio"] >= 1.2)
    ),

    (
        "VOL >=30k + B/S >=1.3",
        (df["volume"] >= 30000)
        & (df["bs_ratio"] >= 1.3)
    ),

    (
        "MC <40k + VOL >=30k + B/S >=1.2",
        (df["market_cap"] < 40000)
        & (df["volume"] >= 30000)
        & (df["bs_ratio"] >= 1.2)
    ),

    (
        "MC 35-40k + VOL >=30k + B/S >=1.2",
        (df["market_cap"] >= 35000)
        & (df["market_cap"] < 40000)
        & (df["volume"] >= 30000)
        & (df["bs_ratio"] >= 1.2)
    ),

    (
        "LIQ >=10k + VOL >=30k",
        (df["liquidity"] >= 10000)
        & (df["volume"] >= 30000)
    ),

    (
        "LIQ >=10k + VOL >=30k + B/S >=1.2",
        (df["liquidity"] >= 10000)
        & (df["volume"] >= 30000)
        & (df["bs_ratio"] >= 1.2)
    ),

    (
        "FS >=66 + VOL >=30k",
        (df["final_score"] >= 66)
        & (df["volume"] >= 30000)
    ),

    (
        "FS >=66 + VOL >=30k + B/S >=1.2",
        (df["final_score"] >= 66)
        & (df["volume"] >= 30000)
        & (df["bs_ratio"] >= 1.2)
    ),

    (
        "FS >=66 + MC <40k + VOL >=30k",
        (df["final_score"] >= 66)
        & (df["market_cap"] < 40000)
        & (df["volume"] >= 30000)
    ),
]


for name, mask in regimes:
    evaluate_regime(name, mask)


# ============================================================
# 11. FIND BEST DISCOVERY REGIMES
# ============================================================

print()
print("=" * 90)
print("AUTOMATIC REGIME SEARCH")
print("=" * 90)

results = []

mc_ranges = [
    ("ALL", True),
    ("MC<35k", df["market_cap"] < 35000),
    (
        "MC35-40k",
        (df["market_cap"] >= 35000)
        & (df["market_cap"] < 40000)
    ),
    (
        "MC40-50k",
        (df["market_cap"] >= 40000)
        & (df["market_cap"] < 50000)
    ),
    ("MC<40k", df["market_cap"] < 40000),
]

volume_ranges = [
    ("ALL", True),
    ("VOL<20k", df["volume"] < 20000),
    (
        "VOL20-30k",
        (df["volume"] >= 20000)
        & (df["volume"] < 30000)
    ),
    (
        "VOL30-50k",
        (df["volume"] >= 30000)
        & (df["volume"] < 50000)
    ),
    ("VOL30k+", df["volume"] >= 30000),
    ("VOL50k+", df["volume"] >= 50000),
]

bs_ranges = [
    ("ALL", True),
    ("BS>=1.0", df["bs_ratio"] >= 1.0),
    ("BS>=1.2", df["bs_ratio"] >= 1.2),
    ("BS>=1.3", df["bs_ratio"] >= 1.3),
    ("BS>=1.5", df["bs_ratio"] >= 1.5),
]

score_ranges = [
    ("ALL", True),
    ("FS>=64", df["final_score"] >= 64),
    ("FS>=66", df["final_score"] >= 66),
    ("FS>=68", df["final_score"] >= 68),
]


for mc_name, mc_mask in mc_ranges:

    for vol_name, vol_mask in volume_ranges:

        for bs_name, bs_mask in bs_ranges:

            for fs_name, fs_mask in score_ranges:

                mask = (
                    mc_mask
                    if isinstance(mc_mask, pd.Series)
                    else np.ones(len(df), dtype=bool)
                )

                if isinstance(vol_mask, pd.Series):
                    mask = mask & vol_mask

                if isinstance(bs_mask, pd.Series):
                    mask = mask & bs_mask

                if isinstance(fs_mask, pd.Series):
                    mask = mask & fs_mask

                sub = df[mask]

                # Avoid tiny samples.
                if len(sub) < 20:
                    continue

                two = sub["returned_2x"].mean()
                five = sub["returned_5x"].mean()
                rug = sub["rugged"].mean()

                proxy = np.where(
                    sub["returned_5x"] == 1,
                    4,
                    np.where(
                        sub["returned_2x"] == 1,
                        1,
                        np.where(
                            sub["rugged"] == 1,
                            -1,
                            0
                        )
                    )
                ).sum()

                results.append({
                    "regime":
                        f"{mc_name} + "
                        f"{vol_name} + "
                        f"{bs_name} + "
                        f"{fs_name}",

                    "N": len(sub),
                    "2x": two * 100,
                    "5x": five * 100,
                    "rug": rug * 100,
                    "avg_max":
                        sub["max_return"].mean(),
                    "proxy": proxy,
                })


if results:

    results_df = pd.DataFrame(results)

    results_df = results_df.sort_values(
        ["proxy", "5x", "2x"],
        ascending=False
    )

    print()
    print(
        "TOP DISCOVERY REGIMES "
        "(minimum N=20)"
    )

    print("-" * 90)

    for _, row in results_df.head(20).iterrows():

        print(
            f"{row['regime']:55s} "
            f"N={int(row['N']):3d} "
            f"2x={row['2x']:6.2f}% "
            f"5x={row['5x']:6.2f}% "
            f"rug={row['rug']:6.2f}% "
            f"avgMax={row['avg_max']:9.2f}% "
            f"proxy={row['proxy']:7.2f}"
        )

    results_df.to_csv(
        "analytics/s7_models/"
        "pattern_discovery_regimes_v1.csv",
        index=False
    )

    print()
    print(
        "Saved:"
        " analytics/s7_models/"
        "pattern_discovery_regimes_v1.csv"
    )


# ============================================================
# 12. TOP INDIVIDUAL SIGNALS
# ============================================================

print()
print("=" * 90)
print("TOP HISTORICAL OUTCOMES — CONTEXT ONLY")
print("=" * 90)

top = df.sort_values(
    "max_return",
    ascending=False
).head(20)

for _, r in top.iterrows():

    print(
        f"{str(r['symbol'])[:16]:16s} "
        f"FS={r['final_score']:5.1f} "
        f"MC=${r['market_cap']:9.0f} "
        f"VOL=${r['volume']:9.0f} "
        f"BS={r['bs_ratio']:.2f} "
        f"LIQ=${r['liquidity']:9.0f} "
        f"MAX={r['max_return']:9.2f}% "
        f"2x={int(r['returned_2x'])} "
        f"5x={int(r['returned_5x'])} "
        f"RUG={int(r['rugged'])}"
    )


# ============================================================
# 13. SAVE COMPLETE DATASET
# ============================================================

output = (
    "analytics/s7_models/"
    "pattern_discovery_v1.csv"
)

df.to_csv(
    output,
    index=False
)

print()
print("=" * 90)
print("DONE")
print("=" * 90)

print(
    "Saved full discovery dataset:"
)
print(output)

print()
print(
    "IMPORTANT:"
)
print(
    "These results are discovery statistics."
)
print(
    "Do NOT modify S6 from this output alone."
)
print(
    "Next step is out-of-sample validation of the strongest patterns."
)

con.close()
