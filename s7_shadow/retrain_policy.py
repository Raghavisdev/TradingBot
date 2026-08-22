"""
S7 Shadow ML Model Retraining Policy

Implements a SAFE candidate-retraining mechanism.
- Triggered manually.
- Checks if >= 50 new completed outcomes exist in the canonical dataset since the last production model.
- Checks if >= 7 days have passed since the last production model.
- Retrains a candidate model on the entire canonical dataset.
- Candidate is evaluated against an unseen temporal split.
- (Manual) Promotion is required via ModelRegistry.
"""

import sqlite3
import time
from datetime import datetime, timezone, timedelta
import pandas as pd

from analytics.profitability_model.model_registry import ModelRegistry
from analytics.profitability_model.build_dataset import ProfitabilityDatasetBuilder

MIN_NEW_OUTCOMES = 50
MIN_COOLDOWN_DAYS = 7

def check_eligibility():
    """Checks if retraining is eligible based on new completed outcomes and time cooldown."""
    registry = ModelRegistry()
    
    # Get last production model timestamp
    try:
        _, best_meta = registry.get_production_model('1m', 'T_rugged')
        last_promoted_ts_str = best_meta.get("created_at")
        last_promoted_ts = datetime.fromisoformat(last_promoted_ts_str)
    except Exception as e:
        print(f"No existing production model found or error: {e}. Cooldown ignored.")
        last_promoted_ts = datetime(2000, 1, 1, tzinfo=timezone.utc)
    
    # 1. Cooldown Check
    now = datetime.now(timezone.utc)
    days_since = (now - last_promoted_ts).days
    
    if days_since < MIN_COOLDOWN_DAYS:
        print(f"❌ Cooldown not met. {days_since} days since last promotion. Need {MIN_COOLDOWN_DAYS}.")
        return False
        
    print(f"✅ Cooldown met. {days_since} days since last promotion.")
    
    # 2. Outcome Count Check
    # We join signals and outcomes. Outcomes only exist if they are completed.
    conn = sqlite3.connect("database/trading.db")
    
    # Count total outcomes that occurred AFTER the last model was trained.
    # We approximate this by looking at signals.timestamp > last_promoted_ts
    query = """
    SELECT COUNT(*) FROM signals s
    JOIN outcomes o ON s.signal_id = o.signal_id
    WHERE s.timestamp > ?
    """
    
    # Convert last_promoted_ts to timestamp float to match DB if needed, but DB uses ISO string or float.
    # Checking DB format: '2026-08-21...' or float.
    # We will try both if needed, but typically python time.time() is used for s.timestamp if it's float.
    # Let's query one signal to see timestamp format.
    sample = conn.execute("SELECT timestamp FROM signals LIMIT 1").fetchone()
    if sample:
        try:
            float(sample[0])
            is_float = True
        except ValueError:
            is_float = False
    else:
        is_float = True
            
    if is_float:
        cutoff = last_promoted_ts.timestamp()
    else:
        cutoff = last_promoted_ts.isoformat()
        
    count = conn.execute(query, (cutoff,)).fetchone()[0]
    conn.close()
    
    if count < MIN_NEW_OUTCOMES:
        print(f"❌ New Outcomes not met. Found {count} new completed outcomes. Need {MIN_NEW_OUTCOMES}.")
        return False
        
    print(f"✅ New Outcomes met. Found {count} new completed outcomes.")
    return True

def run_candidate_training():
    print("=========================================")
    print("🚀 S7 SHADOW: CANDIDATE MODEL RETRAINING")
    print("=========================================")
    
    if not check_eligibility():
        print("Aborting retraining due to eligibility checks.")
        return False
        
    print("\n[Step 1] Building Canonical Dataset...")
    builder = ProfitabilityDatasetBuilder("database/trading.db")
    builder.build()
    
    print("\n[Step 2] Training Candidate Models...")
    # Import main training script to execute training
    from analytics.profitability_model.train_profitability_models import main as train_models
    train_models()
    
    print("\n=========================================")
    print("✅ Training Complete.")
    print("Models have been registered as candidates in the ModelRegistry.")
    print("They will NOT affect live S7 inference until explicitly promoted using:")
    print("ModelRegistry.promote_to_production(model_id)")
    print("=========================================")
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Force training ignoring cooldown/count")
    args = parser.parse_args()
    
    if args.force:
        print("⚠️ FORCE MODE: Ignoring eligibility checks.")
        print("\n[Step 1] Building Canonical Dataset...")
        builder = ProfitabilityDatasetBuilder("database/trading.db")
        builder.build()
        print("\n[Step 2] Training Candidate Models...")
        from analytics.profitability_model.train_profitability_models import main as train_models
        train_models()
    else:
        run_candidate_training()
