import numpy as np

def engineer_labels(outcome):
    if not outcome:
        return {
            'Y_2x': np.nan,
            'Y_5x': np.nan,
            'Y_10x': np.nan,
            'Y_rug': np.nan,
            'label_max_return': np.nan,
            'label_rugged': np.nan,
            'label_resolved': 0
        }
    
    labels = {}
    labels['Y_2x'] = 1 if outcome.get('returned_2x') == 1 else 0
    labels['Y_5x'] = 1 if outcome.get('returned_5x') == 1 else 0
    labels['Y_10x'] = 1 if outcome.get('returned_10x') == 1 else 0
    labels['Y_rug'] = 1 if outcome.get('rugged') == 1 else 0
    
    labels['label_max_return'] = float(outcome.get('max_return')) if outcome.get('max_return') is not None else np.nan
    labels['label_rugged'] = float(outcome.get('rugged')) if outcome.get('rugged') is not None else np.nan
    labels['label_resolved'] = 1
    
    return labels
