# Canonical Dataset Quality Report
**Generated:** 2026-08-20 16:57:41 UTC
**Database:** `database/trading.db` (6.3 MB)

## 1. Pipeline Statistics
- Total signals evaluated: 38
- Duplicate signals rejected: 0
- Signals missing outcomes rejected: 18
- **Usable training examples: 20**

## 2. Temporal Alignment
- Signals with valid T0 snapshot (<=120s lag): 0 (0.0%)
- Signals with valid T0 intelligence (<=120s lag): 0 (0.0%)
- Average T0 snapshot lag: nans

## 3. Chronological Splits
No random splitting. Strictly ordered by `signal_timestamp`.

- **TRAIN** (60%): 12 signals | 2026-08-05 19:53:16 to 2026-08-06 21:29:58
- **VALIDATION** (20%): 4 signals | 2026-08-06 22:17:25 to 2026-08-07 21:03:39
- **TEST** (20%): 4 signals | 2026-08-07 21:54:16 to 2026-08-07 22:42:06

## 4. Target Distributions (from 20 usable signals)
- **T_positive_return**: 14 (70.0%)
- **T_reached_2x**: 4 (20.0%)
- **T_reached_5x**: 2 (10.0%)
- **T_reached_10x**: 2 (10.0%)
- **T_rugged**: 17 (85.0%)

## 5. Feature Coverage Analysis
Percentage of missing values per feature window:
- Window `t0`: 100.0% missing on average
- Window `30s`: 100.0% missing on average

**Top 10 highest missingness features:**
- `F_t0_snap_mc`: 100.0%
- `F_t0_snap_price`: 100.0%
- `F_t0_snap_liq`: 100.0%
- `F_t0_snap_vol`: 100.0%
- `F_t0_snap_buys`: 100.0%
- `F_t0_snap_sells`: 100.0%
- `F_t0_snap_health`: 100.0%
- `F_snap_0s_mc`: 100.0%
- `F_snap_0s_price`: 100.0%
- `F_snap_0s_liq`: 100.0%

## 6. Leakage Audit
- **T0 Snapshot Leakage:** T0 constrained to [0, +120s] from signal time.
- **Window Leakage:** Window snapshot queries explicitly filter `timestamp <= signal_time + window`.
- **Label Leakage:** Target building is entirely isolated in `targets.py`. Output CSV columns prefixed with `T_` never enter the `F_` feature block.
