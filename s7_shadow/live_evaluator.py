"""
S7 Shadow Live Evaluator — Phase 4A (v2 upgrade)

Architecture:
    signal arrives
        │
        ├─► S6 evaluation (independent, preserved — controls actual trades)
        │
        └─► V2 ML shadow (observer only)
                │
                ├─ T0 temporal sandbox (in-memory SQLite, only data ≤ decision_timestamp)
                ├─ build_all_features()  ←  canonical feature builder
                ├─ ShadowInference(horizon='1m')  ←  v1 or v2 models
                ├─ hypothetical_allocation  (NEVER passed to LiveTrader)
                └─ INSERT INTO s7_shadow_decisions

CRITICAL SAFETY RULES:
  - shadow_allocation is always 0.0
  - hypothetical_allocation is stored for analysis ONLY, never executed
  - No import of LiveTrader, LiveExecutor, LiveSigner, SolanaSender
  - Runs in a daemon thread; cannot block live execution
"""
import os
import sys
import sqlite3
import threading
import time
import json
import traceback
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE

# ── S6 baseline ───────────────────────────────────────────────────────────────
from analytics.paper_lab.strategies import Strategy_S6_Moonshot_Ladder
from analytics.paper_lab.lab_portfolio import LabPortfolio

# ── Canonical ML stack ────────────────────────────────────────────────────────
from analytics.profitability_model.inference import ShadowInference
from analytics.profitability_model.feature_builder import build_all_features, WINDOWS_SECONDS

# ── Execution Intelligence (for snapshot metadata) ────────────────────────────
from s7_shadow.execution_intelligence import ExecutionIntelligence

# ── Constants ─────────────────────────────────────────────────────────────────
FEATURE_VERSION  = "v1"
DATASET_VERSION  = "v2_2026_08_21"

# Hypothetical sizing table — NEVER executed, stored for analysis only
HYPOTHETICAL_ALLOCATION = {
    "HIGH_OPPORTUNITY": 14.0,
    "CANDIDATE":         5.0,
    "OBSERVE":           2.0,
    "AVOID":             0.0,
}

# Logged stages for structured error reporting
STAGE_FEATURE_BUILD   = "FEATURE_BUILD"
STAGE_MODEL_LOAD      = "MODEL_LOAD"
STAGE_INFERENCE       = "INFERENCE"
STAGE_DATABASE_WRITE  = "DATABASE_WRITE"

# ── Module-level singletons (loaded once at import time) ──────────────────────
try:
    _s6_scorer = Strategy_S6_Moonshot_Ladder()
    print(f"[S7 SHADOW] Loaded baseline S6 {_s6_scorer.strategy_id} v{_s6_scorer.strategy_version}")
except Exception as _e:
    print(f"[S7 SHADOW] WARNING: S6 load failed: {_e}")
    _s6_scorer = None

try:
    _ml_scorer = ShadowInference(horizon='1m')
    print(f"[S7 SHADOW] Loaded canonical ML inference engine. Ready: {_ml_scorer.ready}")
except Exception as _e:
    print(f"[S7 SHADOW] WARNING: ML Inference load failed: {_e}")
    _ml_scorer = None


def evaluate_and_record_shadow_decision(coin, s6_allocation: float, s6_decision: str):
    """
    Non-blocking entry point called from pipeline.py after S6 evaluation.

    Parameters
    ----------
    coin          : Signal/Coin object (attributes: signal_id, symbol, ...)
    s6_allocation : dollar amount S6 allocated (or 0.0 if rejected)
    s6_decision   : S6 decision string e.g. 'BUY', 'SKIP', 'AVOID'

    Safety contract
    ---------------
    - Does NOT call LiveTrader, LiveExecutor, LiveSigner, SolanaSender
    - shadow_allocation is always 0.0
    - hypothetical_allocation is stored in DB for analysis, never executed
    - Runs in daemon thread — cannot block pipeline
    """
    def _run():
        stage = STAGE_FEATURE_BUILD
        signal_id = getattr(coin, 'signal_id', 'UNKNOWN')
        symbol    = getattr(coin, 'symbol', 'UNKNOWN')

        try:
            from database.database import database

            # ── T0 timestamp ──────────────────────────────────────────────────
            t0_timestamp = time.time()  # Unix float — all feature queries must be ≤ this

            # ── Step 1: T0 Temporal Sandbox ───────────────────────────────────
            # Copy only rows with timestamp ≤ t0_timestamp into an in-memory
            # SQLite database.  This is the hard guarantee that the feature
            # builder can never see future data.
            temp_conn = sqlite3.connect(':memory:')
            temp_conn.row_factory = sqlite3.Row
            temp_conn.execute("""
                CREATE TABLE snapshots (
                    signal_id TEXT, timestamp TEXT,
                    market_cap REAL, price REAL, liquidity REAL,
                    volume REAL, buys REAL, sells REAL,
                    holders REAL, market_health REAL
                )
            """)
            temp_conn.execute("""
                CREATE TABLE intelligence (
                    signal_id TEXT, collected_at REAL,
                    buy_sell_ratio REAL, sentiment_strength REAL,
                    mc_velocity REAL, volume_velocity REAL,
                    liquidity_change REAL, mc_acceleration REAL
                )
            """)

            snapshot_source_timestamp = None
            intel_source_timestamp    = None

            with database.db_lock:
                prod_conn = sqlite3.connect(DATABASE)

                # Snapshots: timestamp is TEXT ISO string — cast via CAST(... AS REAL)
                snaps = prod_conn.execute(
                    """SELECT signal_id, timestamp, market_cap, price, liquidity,
                              volume, buys, sells, holders, market_health
                       FROM snapshots
                       WHERE signal_id = ?
                         AND CAST(timestamp AS REAL) <= ?""",
                    (signal_id, t0_timestamp)
                ).fetchall()
                if snaps:
                    temp_conn.executemany(
                        "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)", snaps
                    )
                    snapshot_source_timestamp = max(float(r[1]) for r in snaps)

                # Intelligence: collected_at is REAL
                intels = prod_conn.execute(
                    """SELECT signal_id, collected_at, buy_sell_ratio, sentiment_strength,
                              mc_velocity, volume_velocity, liquidity_change, mc_acceleration
                       FROM intelligence
                       WHERE signal_id = ?
                         AND CAST(collected_at AS REAL) <= ?""",
                    (signal_id, t0_timestamp)
                ).fetchall()
                if intels:
                    temp_conn.executemany(
                        "INSERT INTO intelligence VALUES (?,?,?,?,?,?,?,?)", intels
                    )
                    intel_source_timestamp = max(float(r[1]) for r in intels)

                prod_conn.close()

            # Temporal safety assertion
            if snapshot_source_timestamp and snapshot_source_timestamp > t0_timestamp:
                raise RuntimeError(
                    f"TEMPORAL LEAK: snapshot_ts {snapshot_source_timestamp} > t0 {t0_timestamp}"
                )
            if intel_source_timestamp and intel_source_timestamp > t0_timestamp:
                raise RuntimeError(
                    f"TEMPORAL LEAK: intel_ts {intel_source_timestamp} > t0 {t0_timestamp}"
                )

            # ── Step 2: S6 Baseline (independent evaluation, preserved) ──────
            coin_dict = vars(coin).copy() if hasattr(coin, '__dict__') else dict(coin)
            mock_portfolio = LabPortfolio("mock_s7")
            mock_portfolio.initial_cash = 500.0
            mock_portfolio.cash = 500.0

            try:
                if _s6_scorer:
                    _s6_scorer.evaluate_entry(coin_dict, mock_portfolio)
            except Exception as s6_err:
                print(f"[S7 SHADOW] S6 eval warning (non-fatal): {s6_err}")

            # ── Step 3: Canonical Feature Generation ─────────────────────────
            stage = STAGE_FEATURE_BUILD
            features = build_all_features(temp_conn, coin_dict, WINDOWS_SECONDS)
            temp_conn.close()

            # Sanity: T0 feature lag must be >= 0
            t0_lag = features.get('t0_snapshot_lag_s', None)

            # Serialize feature snapshot (strip NaN — JSON cannot represent them)
            feature_snapshot_json = json.dumps(
                {k: v for k, v in features.items()
                 if not (isinstance(v, float) and v != v)},   # exclude float NaN
                sort_keys=True
            )

            # ── Step 4: ML Inference ──────────────────────────────────────────
            stage = STAGE_INFERENCE
            if _ml_scorer and _ml_scorer.ready:
                ml_result = _ml_scorer.evaluate_signal(features)
            else:
                ml_result = {
                    "recommendation": "AVOID",
                    "error": "Models not loaded"
                }

            p_rug       = ml_result.get("p_rug")
            p_2x        = ml_result.get("p_2x")
            p_5x        = ml_result.get("p_5x")
            p_10x       = ml_result.get("p_10x")
            exp_return  = ml_result.get("expected_return_linear")   # linear scale
            opp_score   = ml_result.get("opportunity_score")
            rec         = ml_result.get("recommendation", "AVOID")
            model_ver   = ml_result.get("model_version", "unknown")

            # ── Step 5: Allocation values ─────────────────────────────────────
            # shadow_allocation is ALWAYS 0.0 (observer only — never executed)
            shadow_allocation = 0.0

            # hypothetical_allocation: stored for analysis ONLY, never passed to LiveTrader
            hypothetical_allocation = HYPOTHETICAL_ALLOCATION.get(rec, 0.0)

            # ── Step 6: Execution Intelligence Snapshot ───────────────────────
            exec_snapshot = ExecutionIntelligence.calculate_snapshot(coin, s6_allocation)
            execution_snapshot_json = json.dumps(exec_snapshot, sort_keys=True)
            est_entry = exec_snapshot["ESTIMATED"]["estimated_entry_impact"]
            est_exit  = exec_snapshot["ESTIMATED"]["estimated_exit_impact"]
            est_rt    = exec_snapshot["ESTIMATED"]["estimated_round_trip_cost"]

            # ── Step 7: Persist to database ───────────────────────────────────
            stage = STAGE_DATABASE_WRITE
            created_at = datetime.now(timezone.utc).isoformat()

            with database.db_lock:
                conn = sqlite3.connect(DATABASE, timeout=30.0)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO s7_shadow_decisions (
                        signal_id, symbol, decision_timestamp, model_version,
                        opportunity_score, execution_risk_score, net_score,
                        shadow_allocation, hypothetical_allocation,
                        estimated_entry_impact, estimated_exit_impact,
                        estimated_round_trip_cost,
                        s6_decision, s6_allocation,
                        feature_version, dataset_version,
                        feature_snapshot_json, execution_snapshot_json,
                        t0_timestamp, intel_source_timestamp,
                        snapshot_source_timestamp, created_at,
                        p_rug, p_2x, p_5x, p_10x,
                        expected_return, rank_percentile, confidence,
                        recommendation, ml_shadow_allocation
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?,
                        ?,
                        ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?
                    )
                """, (
                    signal_id, symbol, t0_timestamp, model_ver,
                    opp_score, 0.0, opp_score,
                    shadow_allocation, hypothetical_allocation,
                    est_entry, est_exit,
                    est_rt,
                    s6_decision, s6_allocation,
                    FEATURE_VERSION, DATASET_VERSION,
                    feature_snapshot_json, execution_snapshot_json,
                    t0_timestamp, intel_source_timestamp,
                    snapshot_source_timestamp, created_at,
                    p_rug, p_2x, p_5x, p_10x,
                    exp_return, 0.0, 0.0,
                    rec, shadow_allocation,   # ml_shadow_allocation = 0.0
                ))

                if cursor.rowcount == 0:
                    print(f"[S7 SHADOW] Duplicate skipped for {symbol} ({signal_id})")
                else:
                    print(
                        f"[S7 SHADOW] Recorded: {symbol} | "
                        f"ML={rec} p_rug={p_rug:.3f if p_rug is not None else 'N/A'} "
                        f"opp={opp_score:.3f if opp_score is not None else 'N/A'} "
                        f"hyp_alloc=${hypothetical_allocation:.0f} "
                        f"shadow_alloc=$0 | "
                        f"S6={s6_decision} ${s6_allocation:.2f}"
                    )

                conn.commit()
                conn.close()

        except Exception as exc:
            # Structured logging — stage identifies where the failure occurred
            print(
                f"[S7 SHADOW ERROR] signal_id={signal_id} stage={stage} "
                f"type={type(exc).__name__} msg={exc}"
            )
            traceback.print_exc()

    # Fire-and-forget daemon thread — cannot block the live pipeline
    t = threading.Thread(target=_run, name=f"s7-shadow-{getattr(coin, 'symbol', 'UNKNOWN')}")
    t.daemon = True
    t.start()
