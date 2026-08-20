import pandas as pd
import numpy as np

def split_chronological(df, train_frac=0.6, val_frac=0.2, test_frac=0.2):
    """
    Splits dataframe strictly chronologically based on 'signal_timestamp'.
    """
    df = df.sort_values('signal_timestamp').reset_index(drop=True)
    n = len(df)
    
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    
    # Label splits
    df['split'] = 'TEST'
    df.loc[:train_end-1, 'split'] = 'TRAIN'
    df.loc[train_end:val_end-1, 'split'] = 'VALIDATION'
    
    # Report date ranges
    ranges = {}
    for sp in ['TRAIN', 'VALIDATION', 'TEST']:
        sub = df[df['split'] == sp]
        if len(sub) > 0:
            ranges[sp] = {
                'start': pd.to_datetime(sub['signal_timestamp'].min(), unit='s').strftime('%Y-%m-%d %H:%M:%S'),
                'end': pd.to_datetime(sub['signal_timestamp'].max(), unit='s').strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(sub)
            }
        else:
            ranges[sp] = {'start': None, 'end': None, 'count': 0}
            
    return df, ranges

class WalkForwardSplitter:
    """
    Generates expanding or rolling window splits for walk-forward validation.
    """
    def __init__(self, n_splits, train_size, test_size, rolling=False):
        self.n_splits = n_splits
        self.train_size = train_size
        self.test_size = test_size
        self.rolling = rolling
        
    def split(self, df):
        # Implementation for future use (not executed in this phase)
        pass
