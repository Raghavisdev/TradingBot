import pandas as pd
import numpy as np
import os
import joblib

MODEL_VERSION = "S7_SHADOW_V1"
FEATURE_VERSION = "S7_FEATURES_V1"

class LiquiditySlippageModel:
    def __init__(self):
        self.base_fee = 0.01 # 1% standard dex fee
        self.liq_penalty_factor = 0.5
        self.vol_penalty_factor = 0.2

    def fit(self, df_train):
        print("Fitting liquidity model on Train set...")
        pass

    def estimate_cost(self, allocation_usd, liquidity_usd, volume_usd):
        # Prevent div by zero
        liq = max(liquidity_usd, 1.0)
        vol = max(volume_usd, 1.0)
        
        amm_slippage = 2.0 * (allocation_usd / liq)
        vol_penalty = allocation_usd / vol * self.vol_penalty_factor
        
        estimated_entry_impact = amm_slippage + vol_penalty
        estimated_exit_impact = estimated_entry_impact * 1.5
        
        estimated_round_trip_cost = estimated_entry_impact + estimated_exit_impact + (2 * self.base_fee)
        
        # execution risk is scaled to 0-100 based on total cost
        execution_risk_score = min(estimated_round_trip_cost * 1000, 100)
        
        return {
            "estimated_entry_impact": min(estimated_entry_impact, 1.0),
            "estimated_exit_impact": min(estimated_exit_impact, 1.0),
            "estimated_round_trip_cost": min(estimated_round_trip_cost, 1.0),
            "execution_risk_score": execution_risk_score
        }

def train_and_save_model():
    dataset_path = os.path.join(os.path.dirname(__file__), "s7_dataset.csv")
    if not os.path.exists(dataset_path):
        print("Dataset not found!")
        return

    df = pd.read_csv(dataset_path)
    df_train = df[df['split'] == 'train']

    model = LiquiditySlippageModel()
    model.fit(df_train)

    model_path = os.path.join(os.path.dirname(__file__), "liquidity_model.pkl")
    joblib.dump(model, model_path)
    print(f"Saved LiquiditySlippageModel to {model_path}")

if __name__ == "__main__":
    train_and_save_model()
