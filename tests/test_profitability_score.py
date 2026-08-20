import pytest
from analytics.profitability_model.profitability_score import calculate_opportunity_score, ml_recommended_allocation

def test_opportunity_score():
    score = calculate_opportunity_score(p_rug=0.9, p_2x=0.01, p_5x=0.0, p_10x=0.0, expected_return=-0.5)
    # Rug penalty shrinks it heavily
    assert score < 0
    
    score_good = calculate_opportunity_score(p_rug=0.1, p_2x=0.5, p_5x=0.1, p_10x=0.01, expected_return=1.5)
    assert score_good > score

def test_ml_allocation():
    # Baseline allocation is $10
    alloc = ml_recommended_allocation(-5.0, 10.0, max_allocation=15.0)
    assert alloc == 0.0  # Rejected
    
    alloc_good = ml_recommended_allocation(5.0, 10.0, max_allocation=15.0)
    assert alloc_good == 10.0  # Scaled by 1.0 based on multiplier logic
