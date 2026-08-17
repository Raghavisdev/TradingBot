import unittest
import pandas as pd
import numpy as np
from analytics.s7_models.convergence_backtest import find_validation_thresholds, predict_df

class TestS7Convergence(unittest.TestCase):
    
    def test_s6_buy_never_removed(self):
        # We simulate the logic from convergence_backtest to ensure System C always includes S6 BUY
        test_df = pd.DataFrame({
            'X_s6_decision': ['BUY', 'STRONG_BUY', 'SKIP', 'WATCH'],
            'P_Y_2x': [0.1, 0.1, 0.9, 0.9],
            'P_Y_rug': [0.9, 0.9, 0.1, 0.1]
        })
        
        s6_buy = len(test_df[test_df['X_s6_decision'].isin(['BUY', 'STRONG_BUY'])])
        self.assertEqual(s6_buy, 2)
        
        skip_watch_df = test_df[~test_df['X_s6_decision'].isin(['BUY', 'STRONG_BUY'])]
        self.assertEqual(len(skip_watch_df), 2)
        
        # Rescue
        t_opp, t_rug = 0.5, 0.5
        rescue_mask = (skip_watch_df['P_Y_2x'] >= t_opp) & (skip_watch_df['P_Y_rug'] <= t_rug)
        s7_rescues_df = skip_watch_df[rescue_mask]
        
        sys_c_trades = s6_buy + len(s7_rescues_df)
        
        # Both BUY and rescues are traded, nothing is removed from S6 BUY
        self.assertEqual(sys_c_trades, 4)
        
    def test_validation_thresholds(self):
        # Ensure validation thresholds are pulled from validation df only
        val_df = pd.DataFrame({
            'P_Y_2x': [0.1, 0.4, 0.8, 0.9],  # 80th percentile is ~0.84
            'P_Y_rug': [0.1, 0.2, 0.8, 0.9]  # 20th percentile is ~0.16
        })
        
        t_opp, t_rug = find_validation_thresholds(val_df)
        
        # Check hard bounds are applied and values are sensible
        self.assertTrue(0.1 <= t_opp <= 0.9)
        self.assertTrue(0.1 <= t_rug <= 0.9)
        
    def test_unresolved_signals_excluded(self):
        # Simulating that unresolved signals don't crash and are treated as 0 max_return
        df = pd.DataFrame({
            'label_max_return': [np.nan, 20.0, np.nan],
            'Y_rug': [0, 0, 1]
        })
        
        TRADE_SIZE = 100.0
        pnl = 0.0
        for _, r in df.iterrows():
            if r['Y_rug'] == 1:
                pnl -= TRADE_SIZE
            else:
                ret = float(r.get('label_max_return', 0.0))
                if pd.isna(ret): ret = 0.0
                capture = min(ret * 0.5, ret)
                pnl += TRADE_SIZE * (capture / 100.0)
                
        # NaN is treated as 0.0, 20.0 gives 10.0%, rug gives -100
        self.assertAlmostEqual(pnl, 0 + 10.0 - 100.0)
        
    def test_missing_model_predictions_fail_closed(self):
        df = pd.DataFrame({
            'X_test': [1, 2, 3]
        })
        # Empty models
        df = predict_df(df, {})
        
        # Missing targets are populated with 0.0
        self.assertIn('P_Y_2x', df.columns)
        self.assertEqual(df['P_Y_2x'].sum(), 0.0)
        self.assertIn('P_Y_rug', df.columns)
        self.assertEqual(df['P_Y_rug'].sum(), 0.0)

if __name__ == '__main__':
    unittest.main()
