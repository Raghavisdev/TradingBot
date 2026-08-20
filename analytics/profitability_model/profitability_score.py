import numpy as np

def calculate_opportunity_score(p_rug, p_2x, p_5x, p_10x, expected_return):
    """
    Calculates the meta-score based on model predictions.
    Penalizes rugs, rewards high expected return and 2x/5x/10x probabilities.
    """
    # 1. Base Score derived from expected return
    # Assuming expected_return is derived from the robust regression model
    score = expected_return * 100.0  
    
    # 2. Rug Penalty: Exponential decay as p_rug increases
    rug_penalty = np.exp(-5.0 * p_rug) 
    score *= rug_penalty
    
    # 3. Upside Bonus
    upside = (p_2x * 2.0) + (p_5x * 5.0) + (p_10x * 10.0)
    score += upside
    
    return score

def ml_recommended_allocation(score, s6_allocation, max_allocation=0.5):
    """
    OBSERVER ONLY. Do not use in live trading.
    Modulates the S6 allocation based on the ML opportunity score.
    """
    # If score is highly negative/low, reject
    if score <= 0.0:
        return 0.0
        
    # Scale up to max allocation based on score (e.g. score of 5.0 gets full boost)
    multiplier = np.clip(score / 5.0, 0.0, 1.5)
    
    rec = s6_allocation * multiplier
    return np.clip(rec, 0.0, max_allocation)
