import sqlite3
import pandas as pd
import numpy as np

DB = "database/trading.db"

con = sqlite3.connect(DB)

print("=" * 90)
print("S7 EXECUTION COST SENSITIVITY V1")
print("=" * 90)

# ------------------------------------------------------------
# Use the already validated S6 historical trade population.
# We do NOT alter S6 itself here.
# ------------------------------------------------------------

df = pd.read_sql_query("""
SELECT
    id,
    signal_id,
    symbol,
    invested,
    realized_pnl,
    realized_pct,
    mfe,
    mae
FROM paper_lab_trades
WHERE strategy_id = 'S6_Moonshot_Ladder'
  AND status = 'CLOSED'
ORDER BY id
""", con)

con.close()

if df.empty:
    raise SystemExit("No closed S6 trades found.")

df["invested"] = pd.to_numeric(df["invested"], errors="coerce").fillna(0.0)
df["realized_pnl"] = pd.to_numeric(df["realized_pnl"], errors="coerce").fillna(0.0)
df["mfe"] = pd.to_numeric(df["mfe"], errors="coerce").fillna(0.0)

# ------------------------------------------------------------
# Chronological walk-forward split
# ------------------------------------------------------------

split = int(len(df) * 0.65)

discovery = df.iloc[:split].copy()
validation = df.iloc[split:].copy()

print()
print(f"TOTAL S6 TRADES : {len(df)}")
print(f"DISCOVERY       : {len(discovery)}")
print(f"VALIDATION      : {len(validation)}")

# ------------------------------------------------------------
# IMPORTANT:
#
# This is a conservative sensitivity model.
#
# We treat execution cost as:
#
#   entry cost  = invested * cost
#   exit cost   = gross returned capital * cost
#
# Since the stored S6 records do not contain complete execution
# fills for every partial sell, this is deliberately a sensitivity
# analysis rather than a claim about the exact Jupiter execution cost.
# ------------------------------------------------------------

def evaluate(data, cost):
    d = data.copy()

    gross_proceeds = d["invested"] + d["realized_pnl"]

    entry_cost = d["invested"] * cost
    exit_cost = gross_proceeds.clip(lower=0) * cost

    net_pnl = d["realized_pnl"] - entry_cost - exit_cost

    invested = d["invested"].sum()

    return {
        "N": len(d),
        "invested": invested,
        "gross_pnl": d["realized_pnl"].sum(),
        "net_pnl": net_pnl.sum(),
        "ROI": (net_pnl.sum() / invested * 100.0)
            if invested > 0 else 0.0,
        "win_rate": (net_pnl > 0).mean() * 100.0,
        "avg_pnl": net_pnl.mean(),
        "median_pnl": net_pnl.median(),
        "worst": net_pnl.min(),
        "best": net_pnl.max(),
    }

# ------------------------------------------------------------
# Cost sensitivity
# ------------------------------------------------------------

costs = [
    0.00,
    0.005,
    0.010,
    0.020,
    0.030,
]

for name, data in [
    ("DISCOVERY", discovery),
    ("VALIDATION", validation),
    ("FULL", df),
]:

    print()
    print("=" * 90)
    print(name)
    print("=" * 90)

    rows = []

    for cost in costs:
        r = evaluate(data, cost)

        rows.append({
            "cost_per_side": f"{cost*100:.2f}%",
            "N": r["N"],
            "gross_pnl": r["gross_pnl"],
            "net_pnl": r["net_pnl"],
            "ROI": r["ROI"],
            "win_rate": r["win_rate"],
            "avg_pnl": r["avg_pnl"],
            "median_pnl": r["median_pnl"],
            "worst": r["worst"],
            "best": r["best"],
        })

    out = pd.DataFrame(rows)

    print(
        out.to_string(
            index=False,
            formatters={
                "gross_pnl": "{:+.4f}".format,
                "net_pnl": "{:+.4f}".format,
                "ROI": "{:+.2f}%".format,
                "win_rate": "{:.2f}%".format,
                "avg_pnl": "{:+.4f}".format,
                "median_pnl": "{:+.4f}".format,
                "worst": "{:+.4f}".format,
                "best": "{:+.4f}".format,
            }
        )
    )

# ------------------------------------------------------------
# Break-even cost
# ------------------------------------------------------------

print()
print("=" * 90)
print("APPROXIMATE BREAK-EVEN EXECUTION COST")
print("=" * 90)

for name, data in [
    ("DISCOVERY", discovery),
    ("VALIDATION", validation),
    ("FULL", df),
]:

    gross = data["realized_pnl"].sum()
    invested = data["invested"].sum()

    if invested <= 0:
        continue

    # Approximate because exit proceeds differ trade-to-trade.
    gross_proceeds = (data["invested"] + data["realized_pnl"]).clip(lower=0).sum()

    denom = invested + gross_proceeds

    be = gross / denom if denom > 0 else 0.0

    print(
        f"{name:12s} "
        f"gross P&L=${gross:+.4f} "
        f"approx break-even cost/side={be*100:.3f}%"
    )

print()
print("=" * 90)
print("INTERPRETATION")
print("=" * 90)

print("""
This test does NOT claim a specific live trading fee.

It answers a more important question first:

How much execution friction can the existing S6 edge tolerate?

If validation remains positive at conservative costs, we proceed
to a true momentum-allocation replay.

If validation becomes negative quickly, we must improve execution
economics before risking real money.

Do NOT deploy real money from this test alone.
""")
