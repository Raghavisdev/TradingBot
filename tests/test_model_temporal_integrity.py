import pytest
from analytics.profitability_model.train_profitability_models import get_features_for_horizon
import pandas as pd

def test_temporal_integrity():
    # Mock dataframe columns
    cols = ['F_signal_score', 'F_t0_price', 'F_30s_price', 'F_1m_price', 'F_5m_price']
    df = pd.DataFrame(columns=cols)
    
    t0_features = get_features_for_horizon(df, 't0')
    assert 'F_signal_score' in t0_features
    assert 'F_t0_price' in t0_features
    assert 'F_1m_price' not in t0_features
    
    m1_features = get_features_for_horizon(df, '1m')
    assert 'F_t0_price' in m1_features
    assert 'F_1m_price' in m1_features
    assert 'F_5m_price' not in m1_features
