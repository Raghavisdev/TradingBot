import sqlite3
import numpy as np
import pandas as pd

DB = "database/trading.db"

con = sqlite3.connect(DB)

print("=" * 90)
print("S7 WALK-FORWARD VALIDATION V1")
print("=" * 90)

# ============================================================
# BUILD DATASET
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
    s.signal_id,
    s.symbol,
    CAST(s.timestamp AS REAL) AS signal_time,
    CAST(s.gt_score AS REAL) AS gt_score,
    CAST(s.final_score AS REAL) AS final_score,
    CAST(s.signal_market_cap AS REAL) AS signal_market_cap,

    CAST(x.market_cap AS REAL) AS market_cap,
    CAST(x.liquidity AS REAL) AS liquidity,
    CAST(x.volume AS REAL) AS volume,
    CAST(x.buys AS REAL) AS buys,
    CAST(x.sells AS REAL) AS sells,

    CASE
        WHEN x.sells > 0
        THEN CAST(x.buys AS REAL) / CAST(x.sells AS REAL)
        ELSE NULL
    END AS bs_ratio,

    CAST(o.max_return AS REAL) AS max_return,
    CAST(o.min_return AS REAL) AS min_return,
    CAST(o.rugged AS INTEGER) AS rugged,
    CAST(o.returned_2x AS INTEGER) AS returned_2x,
    CAST(o.returned_5x AS INTEGER) AS returned_5x,
    CAST(o.returned_10x AS INTEGER) AS returned_10x

FROM signals s

JOIN first_snap f
    ON f.signal_id = s.signal_id

JOIN snapshots x
    ON x.signal_id = f.signal_id
    AND CAST(x.timestamp AS REAL) = f.t0

JOIN outcomes o
    ON o.signal_id = s.signal_id

WHERE
    o.returned_2x IS NOT NULL
"""

df = pd.read_sql_query(query, con)

print()
print("TOTAL USABLE SIGNALS:", len(df))

if len(df) < 100:
    raise RuntimeError("Too few usable signals.")

# ============================================================
# TIME ORDER
# ============================================================

df = df.sort_values("signal_time").reset_index(drop=True)

# ============================================================
# DISCOVERY / VALIDATION SPLIT
#
# Earlier 60% = discovery
# Later 40%  = untouched validation
# ============================================================

split = int(len(df) * 0.60)

discovery = df.iloc[:split].copy()
validation = df.iloc[split:].copy()

print()
print("=" * 90)
print("TIME SPLIT")
print("=" * 90)

print("Discovery :", len(discovery))
print("Validation:", len(validation))

# ============================================================
# ECONOMIC PROXY
# ============================================================

def proxy(row):
    if int(row.returned_5x or 0):
        return 4.0
    if int(row.returned_2x or 0):
        return 1.0
    if int(row.rugged or 0):
        return -1.0
    return 0.0


# ============================================================
# REGIME DEFINITIONS
# ============================================================

def regimes(d):

    result = {}

    result["BASELINE"] = np.ones(len(d), dtype=bool)

    result["MC_40_50K"] = (
        (d.market_cap >= 40000) &
        (d.market_cap < 50000)
    )

    result["MC_GE_50K"] = (
        d.market_cap >= 50000
    )

    result["VOL_GE_30K"] = (
        d.volume >= 30000
    )

    result["VOL_30_50K"] = (
        (d.volume >= 30000) &
        (d.volume < 50000)
    )

    result["BS_1_0_1_2"] = (
        (d.bs_ratio >= 1.0) &
        (d.bs_ratio < 1.2)
    )

    result["FS_GE_66"] = (
        d.final_score >= 66
    )

    result["FS_GE_68"] = (
        d.final_score >= 68
    )

    result["FS_GE_68_VOL_GE_30K"] = (
        (d.final_score >= 68) &
        (d.volume >= 30000)
    )

    result["MC_GE_40K_VOL_GE_30K"] = (
        (d.market_cap >= 40000) &
        (d.volume >= 30000)
    )

    result["MC_LT_40K_VOL_LT_20K_BS_GE_1_FS_GE_64"] = (
        (d.market_cap < 40000) &
        (d.volume < 20000) &
        (d.bs_ratio >= 1.0) &
        (d.final_score >= 64)
    )

    return result


# ============================================================
# DISCOVERY EVALUATION
# ============================================================

print()
print("=" * 90)
print("DISCOVERY SET")
print("=" * 90)

discovery_results = []

for name, mask in regimes(discovery).items():

    sub = discovery[mask]

    if len(sub) < 10:
        continue

    proxy_value = sum(
        proxy(row)
        for _, row in sub.iterrows()
    )

    discovery_results.append({
        "regime": name,
        "N": len(sub),
        "2x": sub.returned_2x.mean() * 100,
        "5x": sub.returned_5x.mean() * 100,
        "10x": sub.returned_10x.mean() * 100,
        "rug": sub.rugged.mean() * 100,
        "median_max": sub.max_return.median(),
        "proxy": proxy_value,
    })

disc = pd.DataFrame(discovery_results)

disc = disc.sort_values(
    ["proxy", "5x", "2x"],
    ascending=False
)

print(
    disc.to_string(
        index=False,
        formatters={
            "2x": "{:.2f}".format,
            "5x": "{:.2f}".format,
            "10x": "{:.2f}".format,
            "rug": "{:.2f}".format,
            "median_max": "{:.2f}".format,
            "proxy": "{:.2f}".format,
        }
    )
)

# ============================================================
# VALIDATION
# ============================================================

print()
print("=" * 90)
print("UNTOUCHED OUT-OF-SAMPLE VALIDATION")
print("=" * 90)

validation_results = []

for name, mask in regimes(validation).items():

    sub = validation[mask]

    if len(sub) < 5:
        continue

    proxy_value = sum(
        proxy(row)
        for _, row in sub.iterrows()
    )

    validation_results.append({
        "regime": name,
        "N": len(sub),
        "2x": sub.returned_2x.mean() * 100,
        "5x": sub.returned_5x.mean() * 100,
        "10x": sub.returned_10x.mean() * 100,
        "rug": sub.rugged.mean() * 100,
        "median_max": sub.max_return.median(),
        "proxy": proxy_value,
    })

val = pd.DataFrame(validation_results)

val = val.sort_values(
    ["proxy", "5x", "2x"],
    ascending=False
)

print(
    val.to_string(
        index=False,
        formatters={
            "2x": "{:.2f}".format,
            "5x": "{:.2f}".format,
            "10x": "{:.2f}".format,
            "rug": "{:.2f}".format,
            "median_max": "{:.2f}".format,
            "proxy": "{:.2f}".format,
        }
    )
)

# ============================================================
# BASELINE COMPARISON
# ============================================================

base = val[
    val.regime == "BASELINE"
].iloc[0]

print()
print("=" * 90)
print("ROBUSTNESS CHECK")
print("=" * 90)

for _, r in val.iterrows():

    if r.regime == "BASELINE":
        continue

    print()
    print(r.regime)

    print(
        "  2x delta : "
        f"{r['2x'] - base['2x']:+.2f} pp"
    )

    print(
        "  5x delta : "
        f"{r['5x'] - base['5x']:+.2f} pp"
    )

    print(
        "  10x delta: "
        f"{r['10x'] - base['10x']:+.2f} pp"
    )

    print(
        "  Rug delta: "
        f"{r['rug'] - base['rug']:+.2f} pp"
    )

    print(
        "  Proxy    : "
        f"{r['proxy']:+.2f}"
    )

# ============================================================
# SAVE
# ============================================================

out = "analytics/s7_models/walk_forward_validation_v1.csv"

val.to_csv(out, index=False)

print()
print("=" * 90)
print("DONE")
print("=" * 90)
print("Saved:", out)

print()
print(
    "IMPORTANT: validation data was not used to discover "
    "or optimize these regimes."
)

con.close()
