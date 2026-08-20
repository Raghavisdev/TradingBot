import pytest
from analytics.profitability_model.model_registry import ModelRegistry
import os

def test_registry_saves_and_loads(tmp_path):
    from sklearn.linear_model import LogisticRegression
    
    # Override registry dir for testing
    registry = ModelRegistry(registry_dir=str(tmp_path))
    model = LogisticRegression()
    
    metadata = {"horizon": "t0", "target": "T_rugged"}
    model_id = registry.register_model(model, metadata)
    
    loaded_model, loaded_meta = registry.load_model(model_id)
    assert loaded_meta['model_id'] == model_id
    assert loaded_meta['horizon'] == 't0'
    assert loaded_meta['model_filename'].startswith('model_')
