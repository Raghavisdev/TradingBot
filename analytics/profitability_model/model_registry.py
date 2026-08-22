import os
import json
import uuid
import joblib
from datetime import datetime, timezone

class ModelRegistry:
    def __init__(self, registry_dir="analytics/profitability_model/models"):
        self.registry_dir = registry_dir
        os.makedirs(self.registry_dir, exist_ok=True)
        self.registry_file = os.path.join(self.registry_dir, "registry.json")
        self._load_registry()

    def _load_registry(self):
        if os.path.exists(self.registry_file):
            with open(self.registry_file, 'r') as f:
                self.records = json.load(f)
        else:
            self.records = []

    def _save_registry(self):
        with open(self.registry_file, 'w') as f:
            json.dump(self.records, f, indent=2)

    def register_model(self, model, metadata):
        model_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()
        
        model_filename = f"model_{model_id}.joblib"
        model_path = os.path.join(self.registry_dir, model_filename)
        
        joblib.dump(model, model_path)
        
        record = {
            "model_id": model_id,
            "created_at": timestamp,
            "model_filename": model_filename,
            **metadata
        }
        
        self.records.append(record)
        self._save_registry()
        return model_id

    def load_model(self, model_id):
        for r in self.records:
            if r["model_id"] == model_id:
                return joblib.load(os.path.join(self.registry_dir, r["model_filename"])), r
        raise ValueError(f"Model {model_id} not found in registry")
        
    def get_best_model(self, horizon, target, metric="pr_auc"):
        candidates = [r for r in self.records if r.get("horizon") == horizon and r.get("target") == target]
        if not candidates:
            return None, None
            
        best = sorted(candidates, key=lambda x: x.get("validation_metrics", {}).get(metric, -999.0), reverse=True)[0]
        return joblib.load(os.path.join(self.registry_dir, best["model_filename"])), best
        
    def get_production_model(self, horizon, target):
        """Loads the most recently promoted production model, ignoring candidates."""
        candidates = [r for r in self.records if r.get("horizon") == horizon and r.get("target") == target and r.get("is_production") == True]
        if not candidates:
            # Fallback to get_best_model if no explicit production model exists yet (for backward compatibility)
            return self.get_best_model(horizon, target)
            
        # Sort by created_at descending
        best = sorted(candidates, key=lambda x: x.get("created_at", ""), reverse=True)[0]
        return joblib.load(os.path.join(self.registry_dir, best["model_filename"])), best
        
    def promote_to_production(self, model_id):
        """Marks a candidate model as the active production model."""
        for r in self.records:
            if r["model_id"] == model_id:
                r["is_production"] = True
            elif r.get("horizon") == r.get("horizon") and r.get("target") == r.get("target"):
                # Demote others with same horizon/target
                pass # Actually, just keeping the newest one with is_production=True is enough, but we can explicitly set to False
        
        # Proper demotion
        target_r = next((r for r in self.records if r["model_id"] == model_id), None)
        if target_r:
            for r in self.records:
                if r["horizon"] == target_r["horizon"] and r["target"] == target_r["target"]:
                    r["is_production"] = (r["model_id"] == model_id)
            self._save_registry()
            return True
        return False
