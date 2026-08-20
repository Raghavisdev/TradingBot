import sqlite3
import re
import numpy as np
import dateutil.parser
from datetime import timezone

WINDOWS_SECONDS = [0, 30, 60, 180, 300, 600, 900, 1800, 3600]

def parse_ts(ts_str):
    if not ts_str: return 0.0
    try:
        return float(ts_str)
    except (TypeError, ValueError):
        try:
            dt = dateutil.parser.parse(str(ts_str))
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0.0

def safe_float(v, default=np.nan):
    if v is None or v == '' or v == '—' or v == '-': return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default

def extract_regex_value(pattern, text, is_numeric=True):
    if not text:
        return np.nan
    m = re.search(pattern, text)
    if m:
        val = m.group(1).replace(',', '')
        if val in ('—', '-'):
            return np.nan
        if not is_numeric:
            return val
        
        multiplier = 1.0
        if 'K' in val:
            multiplier = 1000.0
            val = val.replace('K', '')
        elif 'M' in val:
            multiplier = 1000000.0
            val = val.replace('M', '')
        elif 'm' in val:
            val = val.replace('m', '')
        elif 'h' in val:
            multiplier = 60.0
            val = val.replace('h', '')
        elif 'd' in val:
            multiplier = 1440.0
            val = val.replace('d', '')
        elif '%' in val:
            val = val.replace('%', '')
            
        try:
            return float(val) * multiplier
        except ValueError:
            return np.nan
    return np.nan

def get_signal_features(signal_row):
    features = {
        'F_gt_score': safe_float(signal_row.get('gt_score')),
        'F_final_score': safe_float(signal_row.get('final_score')),
        'F_s6_bought': 1.0 if signal_row.get('bought') else 0.0,
        'F_signal_mc': safe_float(signal_row.get('signal_market_cap'))
    }
    
    text = signal_row.get('telegram_message', '')
    features['F_tel_mc'] = extract_regex_value(r'MC:\s*\$?([\d\.]+[KM]?)', text)
    features['F_tel_age_min'] = extract_regex_value(r'Age:\s*([\d\.]+[mhd])', text)
    features['F_tel_holders'] = extract_regex_value(r'Holders:\s*([\d\,]+)', text)
    features['F_tel_top10'] = extract_regex_value(r'Top10:\s*([\d\.]+)%', text)
    features['F_tel_bundled'] = extract_regex_value(r'Bundled:\s*([\d\.]+)%', text)
    features['F_tel_jeeters'] = extract_regex_value(r'Jeeters:\s*([\d\.]+)%', text)
    features['F_tel_snipers'] = extract_regex_value(r'Snipers:\s*([\d\.]+)%', text)
    features['F_tel_dev'] = extract_regex_value(r'Dev:\s*([\d\.]+)%', text)
    features['F_tel_safe'] = extract_regex_value(r'Safe:\s*([\d\.]+)%', text)
    return features

def get_window_snapshot_features(con, signal_id, signal_ts, windows_sec):
    # Retrieve all snapshots up to the maximum window + buffer
    max_window = max(windows_sec)
    cutoff = signal_ts + max_window + 60
    
    rows = con.execute('''
        SELECT CAST(timestamp AS REAL) as ts, market_cap, price, liquidity, volume, buys, sells, holders, market_health
        FROM snapshots 
        WHERE signal_id = ? AND CAST(timestamp AS REAL) <= ?
        ORDER BY CAST(timestamp AS REAL) ASC
    ''', (signal_id, cutoff)).fetchall()
    
    # Also find T0 (first snapshot at or after signal_ts, up to +120s)
    t0_lag = np.nan
    t0_snap = None
    for r in rows:
        lag = r['ts'] - signal_ts
        if lag >= -5 and lag <= 120:  # Allow slight early snapshots due to clock sync
            t0_snap = r
            t0_lag = lag
            break
            
    features = {'t0_snapshot_lag_s': t0_lag}
    
    if t0_snap:
        features['F_t0_snap_mc'] = safe_float(t0_snap['market_cap'])
        features['F_t0_snap_price'] = safe_float(t0_snap['price'])
        features['F_t0_snap_liq'] = safe_float(t0_snap['liquidity'])
        features['F_t0_snap_vol'] = safe_float(t0_snap['volume'])
        features['F_t0_snap_buys'] = safe_float(t0_snap['buys'])
        features['F_t0_snap_sells'] = safe_float(t0_snap['sells'])
        features['F_t0_snap_health'] = safe_float(t0_snap['market_health'])
    else:
        features['F_t0_snap_mc'] = np.nan
        features['F_t0_snap_price'] = np.nan
        features['F_t0_snap_liq'] = np.nan
        features['F_t0_snap_vol'] = np.nan
        features['F_t0_snap_buys'] = np.nan
        features['F_t0_snap_sells'] = np.nan
        features['F_t0_snap_health'] = np.nan
        
    for w in windows_sec:
        w_cutoff = signal_ts + w
        w_snap = None
        # Find LAST snapshot before or exactly at cutoff
        for r in reversed(rows):
            if r['ts'] <= w_cutoff:
                w_snap = r
                break
        
        w_str = f"{w}s"
        if w_snap:
            features[f'F_snap_{w_str}_mc'] = safe_float(w_snap['market_cap'])
            features[f'F_snap_{w_str}_price'] = safe_float(w_snap['price'])
            features[f'F_snap_{w_str}_liq'] = safe_float(w_snap['liquidity'])
            features[f'F_snap_{w_str}_vol'] = safe_float(w_snap['volume'])
            features[f'F_snap_{w_str}_buys'] = safe_float(w_snap['buys'])
            features[f'F_snap_{w_str}_sells'] = safe_float(w_snap['sells'])
            features[f'F_snap_{w_str}_health'] = safe_float(w_snap['market_health'])
            
            # Drawdown relative to T0
            if t0_snap and safe_float(t0_snap['price']) > 0:
                p0 = safe_float(t0_snap['price'])
                p1 = safe_float(w_snap['price'])
                features[f'F_snap_{w_str}_ret'] = (p1 - p0) / p0
            else:
                features[f'F_snap_{w_str}_ret'] = np.nan
        else:
            features[f'F_snap_{w_str}_mc'] = np.nan
            features[f'F_snap_{w_str}_price'] = np.nan
            features[f'F_snap_{w_str}_liq'] = np.nan
            features[f'F_snap_{w_str}_vol'] = np.nan
            features[f'F_snap_{w_str}_buys'] = np.nan
            features[f'F_snap_{w_str}_sells'] = np.nan
            features[f'F_snap_{w_str}_health'] = np.nan
            features[f'F_snap_{w_str}_ret'] = np.nan
            
    return features

def get_window_intelligence_features(con, signal_id, signal_ts, windows_sec):
    max_window = max(windows_sec)
    cutoff = signal_ts + max_window + 60
    
    rows = con.execute('''
        SELECT CAST(collected_at AS REAL) as ts, buy_sell_ratio, sentiment_strength, mc_velocity, 
               volume_velocity, liquidity_change, mc_acceleration
        FROM intelligence
        WHERE signal_id = ? AND CAST(collected_at AS REAL) <= ?
        ORDER BY CAST(collected_at AS REAL) ASC
    ''', (signal_id, cutoff)).fetchall()
    
    t0_lag = np.nan
    t0_intel = None
    for r in rows:
        lag = r['ts'] - signal_ts
        if lag >= -5 and lag <= 120:
            t0_intel = r
            t0_lag = lag
            break
            
    features = {'t0_intel_lag_s': t0_lag}
    
    if t0_intel:
        features['F_t0_intel_bs_ratio'] = safe_float(t0_intel['buy_sell_ratio'])
        features['F_t0_intel_sent'] = safe_float(t0_intel['sentiment_strength'])
        features['F_t0_intel_mc_vel'] = safe_float(t0_intel['mc_velocity'])
        features['F_t0_intel_vol_vel'] = safe_float(t0_intel['volume_velocity'])
    else:
        features['F_t0_intel_bs_ratio'] = np.nan
        features['F_t0_intel_sent'] = np.nan
        features['F_t0_intel_mc_vel'] = np.nan
        features['F_t0_intel_vol_vel'] = np.nan
        
    for w in windows_sec:
        w_cutoff = signal_ts + w
        w_intel = None
        for r in reversed(rows):
            if r['ts'] <= w_cutoff:
                w_intel = r
                break
                
        w_str = f"{w}s"
        if w_intel:
            features[f'F_intel_{w_str}_bs_ratio'] = safe_float(w_intel['buy_sell_ratio'])
            features[f'F_intel_{w_str}_sent'] = safe_float(w_intel['sentiment_strength'])
            features[f'F_intel_{w_str}_mc_vel'] = safe_float(w_intel['mc_velocity'])
            features[f'F_intel_{w_str}_vol_vel'] = safe_float(w_intel['volume_velocity'])
        else:
            features[f'F_intel_{w_str}_bs_ratio'] = np.nan
            features[f'F_intel_{w_str}_sent'] = np.nan
            features[f'F_intel_{w_str}_mc_vel'] = np.nan
            features[f'F_intel_{w_str}_vol_vel'] = np.nan
            
    return features

def build_all_features(con, signal_row, windows_sec):
    signal_id = signal_row['signal_id']
    signal_ts = parse_ts(signal_row['timestamp'])
    
    feat = {}
    feat.update(get_signal_features(signal_row))
    feat.update(get_window_snapshot_features(con, signal_id, signal_ts, windows_sec))
    feat.update(get_window_intelligence_features(con, signal_id, signal_ts, windows_sec))
    
    return feat
