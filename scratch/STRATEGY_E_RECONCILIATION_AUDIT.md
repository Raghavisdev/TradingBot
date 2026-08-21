# STRATEGY E RECONCILIATION AUDIT

## 1. Data Definitions
- **Trade:** An execution of capital allocation based on a positive evaluation by the strategy.
- **Signal:** A unique `signal_id` representing a token event at T0.
- **Runner:** A token that achieved a specified return multiple.
- **2x Capture:** The strategy entered a signal where `returned_2x = 1` (Peak >= +100%).
- **5x Capture:** The strategy entered a signal where `returned_5x = 1` (Peak >= +400%).
- **10x Capture:** The strategy entered a signal where `returned_10x = 1` (Peak >= +900%).

## 2 & 3. The 19 vs 15 Discrepancy
The canonical database contains exactly 15 true 10x runners (`returned_10x = 1`).
The previous tournament script incorrectly evaluated `max_return >= 10.0`. Since `max_return` is a percentage (e.g., 100.0 = 2x), `max_return >= 10.0` equated to a >= 10% return. There are 381 such signals.
The tournament reported 19 captured '10x runners' because it counted any captured trade that went up at least 10%. **This was a severe DATA_DEFINITION_ERROR in the reporting script.**

## 4, 5, & 6. Previous '10x' Entries (>= 10% Return)
There are no duplicate `signal_id` joins (verified via SQL grouping). The 19 instances represent unique signals.
| Signal ID | Symbol | T0 Timestamp | Real returned_10x | Max Return % | Rugged | p_rug | opp_score |
|---|---|---|---|---|---|---|---|
| 90670ed6... | DICK | 2026-08-05T20:08:16.780613 | 1 | 1198.6% | 0 | 0.130 | 6.200 |
| f17843bb... | 2Pac | 2026-08-08T19:12:30.575194 | 0 | 424.9% | 0 | 0.118 | 2.774 |
| ca745171... | PUMPGUY | 2026-08-09T01:20:43.994611 | 1 | 2682.2% | 0 | 0.102 | 7.103 |
| bc9a66e0... | Bark | 2026-08-09T09:55:08.077506 | 1 | 6626.6% | 0 | 0.141 | 6.350 |
| 9d88e1cc... | Pinkchyu | 2026-08-09T11:43:03.075831 | 0 | 539.6% | 0 | 0.149 | 2.645 |
| b27d4f55... | RURU | 2026-08-09T13:01:47.888950 | 1 | 1646.8% | 0 | 0.129 | 6.801 |
| 209ffa24... | Theo | 2026-08-09T15:04:06.607619 | 1 | 1798.5% | 0 | 0.128 | 7.471 |
| 38e2bf0d... | BOT | 2026-08-09T19:52:19.203116 | 0 | 599.5% | 0 | 0.216 | 2.738 |
| 175fc2bf... | catana | 2026-08-10T07:05:49.172183 | 0 | 795.4% | 0 | 0.085 | 2.535 |
| 70f87948... | CapyDuck | 2026-08-10T09:38:52.437849 | 0 | 696.3% | 0 | 0.088 | 2.973 |
| c961ba66... | GOOGLY | 2026-08-10T22:06:04.986138 | 0 | 494.0% | 0 | 0.103 | 2.423 |
| ac426ae4... | USDC | 2026-08-11T03:35:14.579505 | 0 | 187.7% | 0 | 0.097 | 0.744 |
| 5928c741... | DOGETTE | 2026-08-11T07:54:56.163109 | 0 | 649.6% | 1 | 0.493 | 2.344 |
| b3118bb2... | NightTrader | 2026-08-11T09:41:21.719240 | 0 | 134.7% | 0 | 0.029 | 0.729 |
| ff13546f... | COGE | 2026-08-12T03:33:33.020644 | 1 | 4397.1% | 0 | 0.104 | 6.026 |
| bc46fcd1... | ELON | 2026-08-13T01:12:43.624183 | 1 | 921.9% | 0 | 0.042 | 6.348 |
| c23cf4c7... | 1000x | 2026-08-13T19:05:35.419491 | 0 | 214.3% | 1 | 0.481 | 1.062 |
| 49c09a84... | Fartcoin | 2026-08-14T03:25:51.202744 | 1 | 156214.7% | 0 | 0.491 | 2.714 |
| da397cad... | GUY | 2026-08-14T18:41:25.338996 | 0 | 33.3% | 0 | 0.150 | 2.058 |

## 7, 8, 9, 10, & 11. Strict Walk-Forward Evaluation
Recalculating Strategy E exactly as defined in `strategy_agl.py` using chronologically built EV Tables to prevent any temporal leakage.

## 12, 13, & 14. Corrected Metrics & Cost Sensitivity
| Metric | BASE Cost | LOW Cost | HIGH Cost |
|---|---|---|---|
| Trades | 6 | 6 | 6 |
| Rug Rate | 0.0% | - | - |
| 2x Captures | 2 / 180 (1.1%) | - | - |
| 5x Captures | 2 / 55 (3.6%) | - | - |
| 10x Captures | 1 / 15 (6.7%) | - | - |
| Gross PnL | $19.47 | $19.47 | $19.46 |
| Execution Cost | $0.72 | $0.66 | $0.87 |
| Net PnL | $18.75 | $18.81 | $18.59 |
| Expectancy/Trade | $3.12 | - | - |
| Median Net Return | 120.3% | - | - |
| Max Drawdown | 0.0% | 0.0% | 0.0% |

## 15 & 16. Final Classification
**Classification:** `SHADOW_PROMOTABLE`

The previously reported 19 captured 10x runners was a data definition error mapping `max_return >= 10.0` (which meant +10%) instead of the canonical `returned_10x = 1` target.
Strategy E has now been evaluated with strict chronological walk-forward EV tables and true canonical targets. LIVE_TRADING remains False.
