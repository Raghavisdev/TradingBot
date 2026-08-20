import os
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import precision_recall_curve, auc, brier_score_loss, roc_auc_score
from analytics.profitability_model.model_registry import ModelRegistry
from analytics.profitability_model.calibration import expected_calibration_error

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

HORIZONS = ['t0', '30s', '1m', '3m', '5m', '10m', '15m']
TARGETS = ['T_rugged', 'T_reached_2x', 'T_reached_5x', 'T_reached_10x']

def load_data():
    df = pd.read_csv('analytics/profitability_model/canonical_dataset.csv')
    return df

def get_features_for_horizon(df, horizon):
    # Base features (always available)
    features = [c for c in df.columns if c.startswith('F_') and not ('_snap_' in c or '_intel_' in c or '_t0_' in c)]
    
    # Horizon features
    if horizon == 't0':
        features += [c for c in df.columns if '_t0_' in c]
    else:
        # Include t0 and the specific horizon
        features += [c for c in df.columns if '_t0_' in c or f'_{horizon}_' in c]
        
    return features

def train_and_evaluate(X_train, y_train, X_val, y_val, model_name, scale_pos_weight=1.0):
    if model_name == 'logistic':
        model = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('clf', LogisticRegression(class_weight='balanced', max_iter=1000))
        ])
    elif model_name == 'rf':
        model = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('clf', RandomForestClassifier(class_weight='balanced', n_estimators=100, random_state=42))
        ])
    elif model_name == 'xgb' and HAS_XGB:
        model = XGBClassifier(
            scale_pos_weight=scale_pos_weight, 
            random_state=42, 
            use_label_encoder=False, 
            eval_metric='logloss',
            missing=np.nan
        )
    else:
        return None, {}
        
    model.fit(X_train, y_train)
    probs_val = model.predict_proba(X_val)[:, 1]
    
    # Metrics
    precision, recall, _ = precision_recall_curve(y_val, probs_val)
    pr_auc = auc(recall, precision)
    try:
        roc_auc = roc_auc_score(y_val, probs_val)
    except ValueError:
        roc_auc = 0.5
    brier = brier_score_loss(y_val, probs_val)
    ece = expected_calibration_error(y_val, probs_val)
    
    metrics = {
        'pr_auc': pr_auc,
        'roc_auc': roc_auc,
        'brier': brier,
        'ece': ece
    }
    
    return model, metrics

def main():
    print("Starting Model Training Pipeline...")
    df = load_data()
    registry = ModelRegistry()
    
    train_df = df[df['split'] == 'TRAIN']
    val_df = df[df['split'] == 'VALIDATION']
    
    if len(train_df) == 0 or len(val_df) == 0:
        print("Error: Train or Val set is empty.")
        return
        
    for target in TARGETS:
        print(f"\\n--- Training for Target: {target} ---")
        y_train = train_df[target].values
        y_val = val_df[target].values
        
        # Calculate pos weight for imbalance
        pos_count = np.sum(y_train)
        neg_count = len(y_train) - pos_count
        scale_pos_weight = neg_count / max(1, pos_count)
        
        for horizon in HORIZONS:
            print(f"Horizon: {horizon}")
            features = get_features_for_horizon(df, horizon)
            
            X_train = train_df[features].values
            X_val = val_df[features].values
            
            best_pr_auc = -1.0
            
            for m_name in ['logistic', 'rf', 'xgb']:
                if m_name == 'xgb' and not HAS_XGB:
                    continue
                    
                model, metrics = train_and_evaluate(X_train, y_train, X_val, y_val, m_name, scale_pos_weight)
                if model is None:
                    continue
                    
                print(f"  {m_name}: PR-AUC={metrics['pr_auc']:.3f}, Brier={metrics['brier']:.3f}")
                
                # Register the model
                metadata = {
                    "horizon": horizon,
                    "target": target,
                    "model_type": m_name,
                    "features": features,
                    "validation_metrics": metrics
                }
                registry.register_model(model, metadata)

if __name__ == "__main__":
    main()
