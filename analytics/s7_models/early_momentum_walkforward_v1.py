import sqlite3
import pandas as pd
import numpy as np

DB = "database/trading.db"

con = sqlite3.connect(DB)

print("=" * 90)
print("S7 EARLY MOMENTUM WALK-FORWARD ECONOMIC VALIDATION V1")
print("=" * 90)

# ============================================================
# DATA
# ============================================================

trades = pd.read_sql_query("""
    SELECT
        signal_id,
        symbol,
        entry_time,
        invested,
        realized_pnl,
        realized_pct,
        mfe,
        mae
    FROM paper_lab_trades
    WHERE strategy_id='S6_Moonshot_Ladder'
      AND status='CLOSED'
    ORDER BY entry_time
""", con)

trades["signal_id"] = trades["signal_id"].astype(str)
trades["entry_time"] = pd.to_numeric(
    trades["entry_time"], errors="coerce"
)

# Use chronological split.
cut = int(len(trades) * 0.65)

discovery = trades.iloc[:cut].copy()
validation = trades.iloc[cut:].copy()

print()
print("TOTAL S6 TRADES :", len(trades))
print("DISCOVERY       :", len(discovery))
print("VALIDATION      :", len(validation))

# ============================================================
# SNAPSHOTS
# ============================================================

snap = pd.read_sql_query("""
    SELECT
        signal_id,
        CAST(timestamp AS REAL) AS timestamp,
        CAST(price AS REAL) AS price,
        CAST(volume AS REAL) AS volume,
        CAST(liquidity AS REAL) AS liquidity,
        CAST(buys AS REAL) AS buys,
        CAST(sells AS REAL) AS sells
    FROM snapshots
    WHERE CAST(price AS REAL) > 0
    ORDER BY signal_id, timestamp
""", con)

snap["signal_id"] = snap["signal_id"].astype(str)

# ============================================================
# EARLY FEATURES
# ============================================================

records = []

for sid, t in trades.groupby("signal_id"):

    if t.empty:
        continue

    tr = t.iloc[0]

    g = snap[snap.signal_id == sid]

    if len(g) < 6:
        continue

    g = g.sort_values("timestamp").reset_index(drop=True)

    p0 = float(g.iloc[0]["price"])

    if p0 <= 0:
        continue

    row = {
        "signal_id": sid,
        "entry_time": tr.entry_time,
        "invested": tr.invested,
        "realized_pnl": tr.realized_pnl,
        "mfe": tr.mfe,
    }

    # Five-snapshot confirmation point.
    x = g.iloc[5]

    row["s5_price_pct"] = (
        float(x["price"]) / p0 - 1.0
    ) * 100.0

    v0 = float(g.iloc[0]["volume"] or 0)
    v5 = float(x["volume"] or 0)

    row["s5_volume_ratio"] = (
        v5 / v0 if v0 > 0 else np.nan
    )

    row["s5_liq"] = float(x["liquidity"] or 0)

    b = float(x["buys"] or 0)
    s = float(x["sells"] or 0)

    if s > 0:
        row["s5_bs"] = b / s
    else:
        row["s5_bs"] = b if b > 0 else 1.0

    records.append(row)

features = pd.DataFrame(records)

df = trades.merge(
    features,
    on="signal_id",
    how="inner",
    suffixes=("", "_feature")
)

df = df.sort_values("entry_time")

cut_time = df["entry_time"].quantile(0.65)

disc = df[df.entry_time <= cut_time].copy()
valid = df[df.entry_time > cut_time].copy()

print()
print("USABLE WITH EARLY FEATURES:", len(df))
print("DISCOVERY:", len(disc))
print("VALIDATION:", len(valid))

# ============================================================
# DISCOVERY
# ============================================================

print()
print("=" * 90)
print("DISCOVERY — EARLY REGIMES")
print("=" * 90)

regimes = {
    "BASELINE": np.ones(len(disc), dtype=bool),

    "PRICE_GE_5":
        disc["s5_price_pct"] >= 5,

    "PRICE_GE_10":
        disc["s5_price_pct"] >= 10,

    "PRICE_GE_20":
        disc["s5_price_pct"] >= 20,

    "PRICE_GE_5_VOL_LT_1.5":
        (disc["s5_price_pct"] >= 5) &
        (disc["s5_volume_ratio"] < 1.5),

    "PRICE_GE_5_VOL_GE_1.5":
        (disc["s5_price_pct"] >= 5) &
        (disc["s5_volume_ratio"] >= 1.5),

    "PRICE_GE_10_VOL_GE_1.5":
        (disc["s5_price_pct"] >= 10) &
        (disc["s5_volume_ratio"] >= 1.5),
}

for name, mask in regimes.items():

    x = disc[mask].copy()

    if len(x) == 0:
        continue

    invested = x.invested.sum()
    pnl = x.realized_pnl.sum()

    print(
        f"{name:<30}"
        f"N={len(x):3d} "
        f"ROI={(pnl/invested*100 if invested else 0):+7.2f}% "
        f"MFE={x.mfe.mean():8.2f}% "
        f"50x={(x.mfe>=50).mean()*100:6.2f}% "
        f"100x={(x.mfe>=100).mean()*100:6.2f}%"
    )

# ============================================================
# VALIDATION
# ============================================================

print()
print("=" * 90)
print("UNTOUCHED OUT-OF-SAMPLE VALIDATION")
print("=" * 90)

validation_regimes = {
    "BASELINE": np.ones(len(valid), dtype=bool),

    "PRICE_GE_5":
        valid["s5_price_pct"] >= 5,

    "PRICE_GE_10":
        valid["s5_price_pct"] >= 10,

    "PRICE_GE_20":
        valid["s5_price_pct"] >= 20,

    "PRICE_GE_5_VOL_LT_1.5":
        (valid["s5_price_pct"] >= 5) &
        (valid["s5_volume_ratio"] < 1.5),

    "PRICE_GE_5_VOL_GE_1.5":
        (valid["s5_price_pct"] >= 5) &
        (valid["s5_volume_ratio"] >= 1.5),

    "PRICE_GE_10_VOL_GE_1.5":
        (valid["s5_price_pct"] >= 10) &
        (valid["s5_volume_ratio"] >= 1.5),
}

baseline_pnl = valid.realized_pnl.sum()
baseline_invested = valid.invested.sum()

print(
    f"BASELINE validation:"
    f" N={len(valid)}"
    f" P&L=${baseline_pnl:+.4f}"
    f" ROI={(baseline_pnl/baseline_invested*100 if baseline_invested else 0):+.2f}%"
)

for name, mask in validation_regimes.items():

    x = valid[mask].copy()

    if len(x) == 0:
        continue

    invested = x.invested.sum()
    pnl = x.realized_pnl.sum()

    roi = (
        pnl / invested * 100
        if invested > 0
        else 0
    )

    print(
        f"{name:<30}"
        f"N={len(x):3d} "
        f"P&L=${pnl:+9.4f} "
        f"ROI={roi:+7.2f}% "
        f"50x={(x.mfe>=50).mean()*100:6.2f}% "
        f"100x={(x.mfe>=100).mean()*100:6.2f}% "
        f"200x={(x.mfe>=200).mean()*100:6.2f}%"
    )

# ============================================================
# CAPITAL-ALLOCATION SIMULATION
# ============================================================

print()
print("=" * 90)
print("CAPITAL ALLOCATION SIMULATION")
print("=" * 90)

print("""
Interpretation:

1. BASE = normal S6 position.
2. CONFIRMED = normal S6 position only when early momentum
   confirms.
3. This is NOT a claim that we can magically buy at S5.
   It is a validation of whether the early state contains
   useful information for managing capital.
""")

# We simulate a conservative overlay:
#
# weak:
#   keep 50% of normal allocation
#
# confirmed:
#   keep 100%
#
# strong:
#   allow 125%
#
# This is NOT deployment code.

def allocation_factor(row):

    p = row.s5_price_pct

    if p < 5:
        return 0.50

    if p < 10:
        return 1.00

    if p < 20:
        return 1.10

    return 1.25


valid = valid.copy()

valid["allocation_factor"] = valid.apply(
    allocation_factor,
    axis=1
)

valid["sim_pnl"] = (
    valid.realized_pnl *
    valid.allocation_factor
)

sim_pnl = valid.sim_pnl.sum()

# Approximate capital exposure.
sim_invested = (
    valid.invested *
    valid.allocation_factor
).sum()

sim_roi = (
    sim_pnl / sim_invested * 100
    if sim_invested > 0
    else 0
)

print(
    f"Baseline:"
    f" P&L=${baseline_pnl:+.4f}"
    f" ROI={(baseline_pnl/baseline_invested*100):+.2f}%"
)

print(
    f"Momentum allocation:"
    f" P&L=${sim_pnl:+.4f}"
    f" ROI={sim_roi:+.2f}%"
)

print(
    f"Delta P&L=${sim_pnl-baseline_pnl:+.4f}"
)

print(
    f"Delta ROI={sim_roi-(baseline_pnl/baseline_invested*100):+.2f} pp"
)

# ============================================================
# SAVE
# ============================================================

out = "analytics/s7_models/early_momentum_walkforward_v1.csv"

valid.to_csv(out, index=False)

print()
print("=" * 90)
print("DONE")
print("=" * 90)
print("Saved:", out)

con.close()
