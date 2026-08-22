import numpy as np
import pandas as pd
from analytics.profitability_model.model_registry import ModelRegistry
from analytics.profitability_model.profitability_score import calculate_expected_value

class ShadowInference:
    def __init__(self, horizon='1m'):
        self.horizon = horizon
        self.registry = ModelRegistry()
        try:
            self.model_rug, self.meta_rug = self.registry.get_production_model(horizon, 'T_rugged')
            self.model_2x, _ = self.registry.get_production_model(horizon, 'T_reached_2x')
            self.model_5x, _ = self.registry.get_production_model(horizon, 'T_reached_5x')
            self.model_10x, _ = self.registry.get_production_model(horizon, 'T_reached_10x')
            self.model_ret, _ = self.registry.get_production_model(horizon, 'T_log_return')
            self.features = self.meta_rug['features']
        except Exception as e:
            self.ready = False
            print("Failed to load models for inference:", e)
        else:
            self.ready = True
            
    def evaluate_signal(self, signal_dict):
        if not self.ready:
            return {"recommendation": "AVOID", "error": "Models not loaded"}
            
        # Convert to DataFrame
        df = pd.DataFrame([signal_dict])
        
        # Ensure all required features are present
        missing = [f for f in self.features if f not in df.columns]
        for m in missing:
            df[m] = np.nan
            
        X = df[self.features].values
        
        # Predict
        p_rug = float(self.model_rug.predict_proba(X)[0, 1])
        p_2x = float(self.model_2x.predict_proba(X)[0, 1])
        p_5x = float(self.model_5x.predict_proba(X)[0, 1])
        p_10x = float(self.model_10x.predict_proba(X)[0, 1])
        e_log_ret = float(self.model_ret.predict(X)[0])
        
        opp_score = float(calculate_expected_value(p_rug, p_2x, p_5x, p_10x, e_log_ret))
        
        # Dummy percentile rank logic - in real deployment this requires state
        # For now, thresholding based on historical score medians
        # AVOID < 0, OBSERVE 0-0.5, CANDIDATE 0.5-1.0, HIGH_OPPORTUNITY > 1.0
        if opp_score < 0:
            rec = "AVOID"
        elif opp_score < 0.2:
            rec = "OBSERVE"
        elif opp_score < 0.5:
            rec = "CANDIDATE"
        else:
            rec = "HIGH_OPPORTUNITY"
            
        return {
            "model_version": self.meta_rug.get('model_id', 'unknown'),
            "p_rug": p_rug,
            "p_2x": p_2x,
            "p_5x": p_5x,
            "p_10x": p_10x,
            "expected_return_linear": float(np.expm1(e_log_ret)),
            "opportunity_score": opp_score,
            "recommendation": rec
        }
