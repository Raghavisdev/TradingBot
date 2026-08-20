import os
import pandas as pd
import numpy as np
from analytics.profitability_model.model_registry import ModelRegistry

def main():
    print("Extracting Feature Importances...")
    registry = ModelRegistry()
    
    model, meta = registry.get_best_model(horizon='1m', target='T_rugged', metric='pr_auc')
    
    if model is None:
        print("No model found to explain.")
        return
        
    features = meta['features']
    
    try:
        # Check if the pipeline has a 'clf' step
        if hasattr(model, 'named_steps'):
            clf = model.named_steps['clf']
        else:
            clf = model
            
        importances = clf.feature_importances_
        df_imp = pd.DataFrame({'feature': features, 'importance': importances})
        df_imp = df_imp.sort_values('importance', ascending=False).head(20)
        
        print(f"\\nTop 20 Features for {meta['model_type']} ({meta['horizon']} horizon):")
        for i, row in df_imp.iterrows():
            print(f"  {row['feature']:<30} {row['importance']:.4f}")
            
    except AttributeError:
        print("Model does not support feature_importances_")

if __name__ == "__main__":
    main()
