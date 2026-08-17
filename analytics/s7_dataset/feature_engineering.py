import re
import numpy as np

def extract_regex_value(pattern, text, is_numeric=True, is_percent=False):
    if not text:
        return np.nan
    m = re.search(pattern, text)
    if m:
        val = m.group(1).replace(',', '')
        if val == '—' or val == '-':
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
        elif 'm' in val: # for age
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

def engineer_features(signal, snapshot, intelligence):
    features = {}
    
    # 1. S6 Baseline Features
    features['X_gt_score'] = float(signal.get('gt_score')) if signal.get('gt_score') is not None else np.nan
    features['X_final_score'] = float(signal.get('final_score')) if signal.get('final_score') is not None else np.nan
    features['X_s6_decision'] = signal.get('decision', 'UNKNOWN')
    features['X_s6_bought'] = 1 if signal.get('bought') else 0
    features['X_signal_market_cap'] = float(signal.get('signal_market_cap')) if signal.get('signal_market_cap') is not None else np.nan
    
    # 2. Telegram Parsing
    text = signal.get('telegram_message', '')
    features['X_tel_mc'] = extract_regex_value(r'MC:\s*\$?([\d\.]+[KM]?)', text)
    features['X_tel_age_min'] = extract_regex_value(r'Age:\s*([\d\.]+[mhd])', text)
    features['X_tel_holders'] = extract_regex_value(r'Holders:\s*([\d\,]+)', text)
    features['X_tel_top10'] = extract_regex_value(r'Top10:\s*([\d\.]+)%', text)
    features['X_tel_bundled'] = extract_regex_value(r'Bundled:\s*([\d\.]+)%', text)
    features['X_tel_first50'] = extract_regex_value(r'First50:\s*([\d\.]+)%', text)
    features['X_tel_jeeters'] = extract_regex_value(r'Jeeters:\s*([\d\.]+)%', text)
    features['X_tel_fresh'] = extract_regex_value(r'Fresh:\s*([\d\.]+%|—|-)', text)
    features['X_tel_snipers'] = extract_regex_value(r'Snipers:\s*([\d\.]+)%', text)
    features['X_tel_insiders'] = extract_regex_value(r'Insiders:\s*([\d\.]+)%', text)
    features['X_tel_dev'] = extract_regex_value(r'Dev:\s*([\d\.]+)%', text)
    features['X_tel_safe'] = extract_regex_value(r'Safe:\s*([\d\.]+)%', text)
    features['X_tel_poor'] = extract_regex_value(r'Poor:\s*([\d\.]+)%', text)
    
    m_cw = re.search(r'🕸\s*(\d+)C\s*·\s*(\d+)W\s*·\s*([\d\.]+)%', text) if text else None
    if m_cw:
        features['X_tel_c'] = float(m_cw.group(1))
        features['X_tel_w'] = float(m_cw.group(2))
        features['X_tel_cw_pct'] = float(m_cw.group(3))
    else:
        features['X_tel_c'] = np.nan
        features['X_tel_w'] = np.nan
        features['X_tel_cw_pct'] = np.nan

    # 3. Snapshot Telemetry
    if snapshot:
        features['X_snap_liquidity'] = snapshot.get('liquidity', np.nan)
        features['X_snap_volume'] = snapshot.get('volume', np.nan)
        features['X_snap_buys'] = snapshot.get('buys', np.nan)
        features['X_snap_sells'] = snapshot.get('sells', np.nan)
    else:
        features['X_snap_liquidity'] = np.nan
        features['X_snap_volume'] = np.nan
        features['X_snap_buys'] = np.nan
        features['X_snap_sells'] = np.nan

    # 4. Intelligence Telemetry
    if intelligence:
        features['X_intel_buy_sell_ratio'] = intelligence.get('buy_sell_ratio', np.nan)
        features['X_intel_mc_velocity'] = intelligence.get('mc_velocity', np.nan)
        features['X_intel_holder_velocity'] = intelligence.get('holder_velocity', np.nan)
        features['X_intel_volume_velocity'] = intelligence.get('volume_velocity', np.nan)
        features['X_intel_buy_velocity'] = intelligence.get('buy_velocity', np.nan)
        features['X_intel_liquidity_change'] = intelligence.get('liquidity_change', np.nan)
        features['X_intel_mc_acceleration'] = intelligence.get('mc_acceleration', np.nan)
        features['X_intel_volume_acceleration'] = intelligence.get('volume_acceleration', np.nan)
        features['X_intel_sentiment_strength'] = intelligence.get('sentiment_strength', np.nan)
    else:
        features['X_intel_buy_sell_ratio'] = np.nan
        features['X_intel_mc_velocity'] = np.nan
        features['X_intel_holder_velocity'] = np.nan
        features['X_intel_volume_velocity'] = np.nan
        features['X_intel_buy_velocity'] = np.nan
        features['X_intel_liquidity_change'] = np.nan
        features['X_intel_mc_acceleration'] = np.nan
        features['X_intel_volume_acceleration'] = np.nan
        features['X_intel_sentiment_strength'] = np.nan

    return features
