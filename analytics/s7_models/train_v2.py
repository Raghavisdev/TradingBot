import os
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import roc_auc_score

def train_models():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_dir = os.path.join(base_dir, 's7_dataset')
    models_dir = os.path.dirname(__file__)
    
    os.makedirs(models_dir, exist_ok=True)
    
    train_path = os.path.join(dataset_dir, 's7_train.csv')
    val_path = os.path.join(dataset_dir, 's7_validation.csv')
    
    if not os.path.exists(train_path):
        print(f"Error: {train_path} not found.")
        return
        
    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path)
    
    # Feature columns
    feature_cols = [c for c in train_df.columns if c.startswith('X_')]
    
    # Exclude non-numeric columns for XGBoost if any
    X_train = train_df[feature_cols].copy()
    X_val = val_df[feature_cols].copy()
    
    # Ensure numeric
    for c in feature_cols:
        X_train[c] = pd.to_numeric(X_train[c], errors='coerce')
        X_val[c] = pd.to_numeric(X_val[c], errors='coerce')
        
    targets = ['Y_2x', 'Y_5x', 'Y_10x', 'Y_rug']
    
    for target in targets:
        print(f"\n{'='*50}\nTraining {target}\n{'='*50}")
        
        y_train = train_df[target]
        y_val = val_df[target]
        
        pos_count = y_train.sum()
        total_count = len(y_train)
        neg_count = total_count - pos_count
        pos_pct = (pos_count / total_count) * 100 if total_count > 0 else 0
        
        print(f"Total labeled rows (Train): {total_count}")
        print(f"Positive count: {pos_count}")
        print(f"Negative count: {neg_count}")
        print(f"Positive percentage: {pos_pct:.2f}%")
        
        # User requirement: minimum 10 positive examples to support meaningful evaluation
        if pos_count < 10:
            print(f"Result: INSUFFICIENT-DATA for {target}. Will not train.")
            continue
            
        print(f"Training XGBoost for {target}...")
        
        # Conservative model complexity for ~429 signals
        model = xgb.XGBClassifier(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=2,
            eval_metric='logloss',
            early_stopping_rounds=10,
            random_state=42
        )
        
        # Enable monotonic constraints for features if we wanted, but not specified
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        
        print(f"Model fitted. Best iteration: {model.best_iteration}")
        
        # Validation AUC
        val_preds = model.predict_proba(X_val)[:, 1]
        
        # Only calculate AUC if both classes exist in val
        if len(np.unique(y_val)) > 1:
            auc = roc_auc_score(y_val, val_preds)
            print(f"Validation ROC-AUC: {auc:.4f}")
        else:
            print("Validation set lacks both classes; cannot compute ROC-AUC.")
            
        model_path = os.path.join(models_dir, f"model_{target}.ubj")
        model.save_model(model_path)
        print(f"Model saved to {model_path}")

if __name__ == "__main__":
    train_models()
