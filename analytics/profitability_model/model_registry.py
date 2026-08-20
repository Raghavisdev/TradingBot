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
