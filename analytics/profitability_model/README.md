# Profitability ML Dataset Builder

This directory contains the canonical, leakage-safe dataset builder for the ML profitability (Observer) layer.

## Architecture
- `build_dataset.py`: Orchestrator. Queries the database, extracts features and targets, splits chronologically, and writes the final CSV + report.
- `feature_builder.py`: Extracts signal-level and temporal window features. Explicitly prevents leakage by using a strict `cutoff` timestamp for snapshot and intelligence queries.
- `targets.py`: Generates prediction targets exclusively from the `outcomes` table. Target columns (`T_`) are isolated from feature columns (`F_`).
- `temporal_split.py`: Contains strictly chronological train/validation/test split logic (60/20/20) and walk-forward infrastructure.

## Key Design Principles
1. **One Row = One Signal:** The `signal_id` is the unit of analysis.
2. **No Future Leakage:** Window features (e.g. `30s`, `1m`) only incorporate snapshots/intelligence recorded *at or before* `signal_time + window`. 
3. **Chronological Splitting:** Random shuffling destroys the temporal structure of financial data. Splits are strictly chronological based on `signal_timestamp`.
4. **Missingness Preservation:** If a window lacks snapshots, the feature is `NaN`. Forward-filling is not used across long gaps.

## Running the Builder
By default, the builder runs against the local development database. On the VPS, run:

```bash
python analytics/profitability_model/build_dataset.py
```
*(Optionally modify the script to point explicitly to `/home/tradingbot/TradingBot/database/trading.db`)*

## Outputs
- `canonical_dataset.csv`: The final feature matrix with targets. Do not commit this file to Git.
- `dataset_report.md`: Quality report detailing alignment, missingness, target distributions, and split dates.
