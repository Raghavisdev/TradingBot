import numpy as np
from sklearn.calibration import IsotonicRegression

def calibrate_probabilities(y_val, probs_val, probs_test):
    """
    Calibrates raw model probabilities using Isotonic Regression fit on validation set.
    """
    iso = IsotonicRegression(out_of_bounds='clip')
    iso.fit(probs_val, y_val)
    
    calibrated_val = iso.predict(probs_val)
    calibrated_test = iso.predict(probs_test)
    
    return calibrated_val, calibrated_test, iso

def expected_calibration_error(y_true, y_prob, n_bins=10):
    """
    Computes Expected Calibration Error (ECE).
    """
    bins = np.linspace(0., 1., n_bins + 1)
    binids = np.digitize(y_prob, bins) - 1
    
    ece = 0.0
    for i in range(n_bins):
        mask = binids == i
        if np.any(mask):
            prob_pred = np.mean(y_prob[mask])
            prob_true = np.mean(y_true[mask])
            ece += np.abs(prob_pred - prob_true) * np.sum(mask)
            
    return ece / len(y_true)
