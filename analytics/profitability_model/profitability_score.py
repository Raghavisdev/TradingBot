import numpy as np

def calculate_expected_value(p_rug, p_2x, p_5x, p_10x, expected_log_return):
    """
    Calculates the empirical Expected Value.
    Because 2x, 5x, 10x are not mutually exclusive (a 10x is also a 2x and 5x),
    we model the marginal probability of stopping at each tier based on the ladder.
    
    If it reaches 10x, the cumulative ladder payout is approx 5.0 units.
    If it reaches 5x but not 10x, the payout is approx 2.0 units.
    If it reaches 2x but not 5x, the payout is approx 0.5 units.
    If it rugs, the payout is -1.0 units.
    
    This is an observational EV formula for ranking, not a true dollar expectation.
    """
    # Marginal probabilities (assuming monotonically decreasing probabilities)
    p_just_2x = np.maximum(0, p_2x - p_5x)
    p_just_5x = np.maximum(0, p_5x - p_10x)
    p_10x_plus = p_10x
    
    # Simple EV formulation
    ev = (p_just_2x * 0.5) + (p_just_5x * 2.0) + (p_10x_plus * 5.0) - (p_rug * 1.0)
    
    # Blend with the robust log regressor to incorporate all the 'partial' wins
    # Convert log return back to linear for blending
    expected_linear_return = np.expm1(expected_log_return)
    
    # Final opportunity score is a 50/50 blend of classifier EV and regressor EV
    composite_score = (ev * 0.5) + (expected_linear_return * 0.5)
    
    return composite_score
