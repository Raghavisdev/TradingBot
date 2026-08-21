# S6 Moonshot Ladder (v1.2) - FROZEN SPECIFICATION

## Identifiers
- **Strategy ID:** `S6_Moonshot_Ladder`
- **Strategy Version:** `1.2`
- **Frozen Date:** 2026-08-21
- **Status:** PRODUCTION CANDIDATE

## Portfolio Limits
- **Virtual Bankroll (Initial Cash):** $500.00
- **Max Simultaneous Positions:** 8
- **Max Total Deployed Capital:** 15.0%

## Entry Rules
- **Prerequisites:**
  - `valid` must not be False.
  - `symbol` must exist.
  - `final_score` must be >= 60.0.

- **Entry Quality (Q) Calculation (0.0 to 1.0):**
  - **Buy/Sell Ratio (30% weight):**
    - Ratio < 0.8 -> 0.2
    - Ratio < 1.2 -> 0.5
    - Ratio < 1.5 -> 0.8
    - Ratio >= 1.5 -> 1.0
  - **Liquidity (25% weight):**
    - < $1k -> 0.2
    - < $10k -> 0.6
    - >= $10k -> 1.0
  - **Market Cap (15% weight):**
    - $35k to $44k -> 1.0 (Optimal)
    - Bell curve dropoff outside this range.
  - **GT Stars (15% weight):**
    - 3 stars -> 1.0
    - 2 stars -> 0.6
    - 1 star -> 0.2
  - **Final Score (15% weight):**
    - >= 70 -> 1.0
    - >= 65 -> 0.7
    - >= 60 -> 0.3

- **Allocation Tiers (Unscaled Base):**
  - Q < 0.35 -> $2.00
  - Q < 0.60 -> $5.00
  - Q < 0.80 -> $9.00
  - Q >= 0.80 -> $14.00

- **Multipliers & Scaling:**
  - B/S Ratio Multiplier: <1.0 -> 0.75x, <1.2 -> 1.0x, <1.5 -> 1.25x, >=1.5 -> 1.50x
  - Equity Drawdown Scaling (relative to peak equity):
    - >= 95% -> 1.00x
    - >= 90% -> 0.75x
    - >= 80% -> 0.50x
    - < 80% -> 0.25x
  - Absolute limits: Min $2.00, Max $18.00.

## Exit Rules
- **Initial Hard Stop:** -20.0%
- **Profit Taking Ladder (relative to original size):**
  - Hit +20% -> Sell 20%
  - Hit +50% -> Sell 10%
  - Hit +100% -> Sell 10%
  - Hit +200% -> Sell 10%
  - Hit +500% -> Sell 10%
  - Hit +1000% -> Sell 10%
- **Moonbag:** Remaining 30% held indefinitely (subject to trailing stop).

- **Dynamic Trailing Stop (Distance from Peak):**
  - Evaluated only after peak hits +20%.
  - Peak +20% to +50% -> 15% trail
  - Peak +50% to +100% -> 20% trail
  - Peak +100% to +300% -> 30% trail
  - Peak +300% to +1000% -> 35% trail
  - Peak > +1000% -> 40% trail
  - Stop level strictly monotonically non-decreasing.

## Model Dependencies
- Currently none (S6 v1.2 is a pure heuristic/rules-based engine).
