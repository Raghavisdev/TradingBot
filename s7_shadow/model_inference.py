import os
import xgboost as xgb
import numpy as np
import pandas as pd
from analytics.s7_dataset.feature_engineering import engineer_features

class S7Predictor:
    def __init__(self):
        self.models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'analytics', 's7_models')
        self.models = {}
        self.targets = ['Y_2x', 'Y_5x', 'Y_10x', 'Y_rug']
        self.is_ready = self._load_models()

    def _load_models(self):
        ready = True
        for target in self.targets:
            model_path = os.path.join(self.models_dir, f"model_{target}.ubj")
            if os.path.exists(model_path):
                try:
                    model = xgb.XGBClassifier()
                    model.load_model(model_path)
                    self.models[target] = model
                except Exception as e:
                    print(f"S7Predictor Error loading {target}: {e}")
                    ready = False
            else:
                ready = False
        return ready

    def predict(self, signal_dict, snapshot_dict, intelligence_dict):
        """
        Ingests raw telemetry dictionaries, exactly as done in training.
        Returns a dictionary of probabilities or None if unavailable.
        """
        if not self.is_ready:
            return None
            
        try:
            # 1. Exact same feature engineering as training
            features = engineer_features(signal_dict, snapshot_dict, intelligence_dict)
            
            # 2. Convert to DataFrame (XGBoost expects 2D)
            df = pd.DataFrame([features])
            
            # Ensure numeric
            for c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
                
            # Keep only X_ features in alphabetical order or as expected by model
            # Since we didn't save feature names strictly, XGBoost handles it if columns match
            feature_cols = [c for c in df.columns if c.startswith('X_')]
            X_infer = df[feature_cols]
            
            # 3. Inference
            predictions = {}
            for target in self.targets:
                # Use predict_proba, taking the probability of class 1
                prob = self.models[target].predict_proba(X_infer)[0, 1]
                predictions[target] = float(prob)
                
            # Provide an auditable S7 recommendation
            # Veto rug, accept 2x > 0.5
            recommendation = 'WATCH'
            if predictions.get('Y_rug', 0) > 0.8:
                recommendation = 'SKIP'
            elif predictions.get('Y_2x', 0) > 0.5:
                recommendation = 'BUY'
                
            predictions['recommendation'] = recommendation
            
            return predictions
            
        except Exception as e:
            # Fail closed
            print(f"S7Predictor inference failed: {e}")
            return None
