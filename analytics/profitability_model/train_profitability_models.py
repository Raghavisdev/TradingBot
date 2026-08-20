import os
import pandas as pd
import numpy as np
import joblib
from xgboost import XGBClassifier, XGBRegressor
from sklearn.metrics import precision_recall_curve, auc, brier_score_loss, mean_absolute_error, r2_score
from analytics.profitability_model.model_registry import ModelRegistry

HORIZONS = ['1m'] # We will focus on 1m as per Phase 2 to save compute on the VPS
CLASSIFIER_TARGETS = ['T_rugged', 'T_reached_2x', 'T_reached_5x', 'T_reached_10x']
REGRESSOR_TARGETS = ['T_log_return']

def load_data():
    df = pd.read_csv('analytics/profitability_model/canonical_dataset.csv')
    
    # Construct robust return target
    # If a signal rugged, max_return is bounded at -0.99 for log1p safety
    if 'T_max_return' in df.columns:
        df['T_log_return'] = np.log1p(np.maximum(df['T_max_return'], -0.99))
    else:
        # Proxy if max_return is not explicitly in dataset
        # rugs = -0.99, 10x = 9.0, 5x = 4.0, 2x = 1.0, positive (not 2x) = 0.5
        ret = np.zeros(len(df))
        ret[df['T_rugged'] == 1] = -0.99
        ret[(df['T_rugged'] == 0) & (df['T_positive_return'] == 1)] = 0.5
        ret[df['T_reached_2x'] == 1] = 1.0
        ret[df['T_reached_5x'] == 1] = 4.0
        ret[df['T_reached_10x'] == 1] = 9.0
        df['T_log_return'] = np.log1p(ret)
        
    return df

def get_features_for_horizon(df, horizon):
    features = [c for c in df.columns if c.startswith('F_') and not ('_snap_' in c or '_intel_' in c or '_t0_' in c)]
    if horizon == 't0':
        features += [c for c in df.columns if '_t0_' in c]
    else:
        features += [c for c in df.columns if '_t0_' in c or f'_{horizon}_' in c]
    # Keep only numeric
    features = [f for f in features if df[f].dtype in [np.float64, np.int64]]
    return features

def train_xgb_classifier(X_train, y_train, X_val, y_val):
    pos_count = max(1, np.sum(y_train))
    neg_count = len(y_train) - pos_count
    scale_pos_weight = neg_count / pos_count
    
    model = XGBClassifier(
        scale_pos_weight=scale_pos_weight, 
        random_state=42, 
        use_label_encoder=False, 
        eval_metric='logloss',
        missing=np.nan,
        n_estimators=100,
        max_depth=4
    )
    model.fit(X_train, y_train)
    probs = model.predict_proba(X_val)[:, 1]
    
    precision, recall, _ = precision_recall_curve(y_val, probs)
    pr_auc = auc(recall, precision)
    brier = brier_score_loss(y_val, probs)
    
    return model, {'pr_auc': pr_auc, 'brier': brier, 'pos_count': int(pos_count), 'neg_count': int(neg_count)}

def train_xgb_regressor(X_train, y_train, X_val, y_val):
    model = XGBRegressor(
        random_state=42,
        missing=np.nan,
        n_estimators=100,
        max_depth=4
    )
    model.fit(X_train, y_train)
    preds = model.predict(X_val)
    
    mae = mean_absolute_error(y_val, preds)
    r2 = r2_score(y_val, preds)
    
    return model, {'mae': mae, 'r2': r2}

def main():
    print("Training Multi-Target Opportunity Models...")
    df = load_data()
    registry = ModelRegistry()
    
    train_df = df[df['split'] == 'TRAIN']
    val_df = df[df['split'] == 'VALIDATION']
    
    for horizon in HORIZONS:
        features = get_features_for_horizon(df, horizon)
        X_train = train_df[features].values
        X_val = val_df[features].values
        
        # Classifiers
        for target in CLASSIFIER_TARGETS:
            print(f"Training {target} ({horizon})")
            y_train = train_df[target].values
            y_val = val_df[target].values
            
            model, metrics = train_xgb_classifier(X_train, y_train, X_val, y_val)
            print(f"  PR-AUC: {metrics['pr_auc']:.3f}")
            
            meta = {"horizon": horizon, "target": target, "model_type": "xgb", "features": features, "validation_metrics": metrics}
            registry.register_model(model, meta)
            
        # Regressor
        for target in REGRESSOR_TARGETS:
            print(f"Training {target} ({horizon})")
            y_train = train_df[target].values
            y_val = val_df[target].values
            
            model, metrics = train_xgb_regressor(X_train, y_train, X_val, y_val)
            print(f"  MAE: {metrics['mae']:.3f}")
            
            meta = {"horizon": horizon, "target": target, "model_type": "xgb_regressor", "features": features, "validation_metrics": metrics}
            registry.register_model(model, meta)

if __name__ == "__main__":
    main()
