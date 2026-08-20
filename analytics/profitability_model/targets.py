import sqlite3
import numpy as np

def safe_float(v, default=np.nan):
    if v is None: return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default

def get_targets(con, signal_id):
    row = con.execute("SELECT * FROM outcomes WHERE signal_id = ?", (signal_id,)).fetchone()
    if not row:
        return None
        
    row_dict = dict(row)
    max_ret = safe_float(row_dict.get('max_return'))
    min_ret = safe_float(row_dict.get('min_return'))
    
    # Core targets
    targets = {
        'T_positive_return': 1 if max_ret > 0 else 0,
        'T_reached_2x': 1 if row_dict.get('returned_2x') else 0,
        'T_reached_5x': 1 if row_dict.get('returned_5x') else 0,
        'T_reached_10x': 1 if row_dict.get('returned_10x') else 0,
        'T_rugged': 1 if row_dict.get('rugged') else 0,
        'T_severe_drawdown': 1 if min_ret < -50.0 else 0,
    }
    
    # Robust heavy-tail target (log1p of max return / 100)
    # e.g. 100% (2x) -> log1p(1) = 0.69
    # e.g. 900% (10x) -> log1p(9) = 2.30
    if not np.isnan(max_ret):
        pos_ret_pct = max(0.0, max_ret / 100.0)
        targets['T_log_max_return'] = np.log1p(pos_ret_pct)
        # We will winsorize globally later, but for now just raw return
        targets['T_raw_max_return'] = max_ret
    else:
        targets['T_log_max_return'] = np.nan
        targets['T_raw_max_return'] = np.nan
        
    return targets
