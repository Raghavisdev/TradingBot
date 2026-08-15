import os
import sqlite3
import pandas as pd
import sys

# Ensure imports work from parent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE

def build_dataset():
    print(f"Connecting to database: {DATABASE}")
    conn = sqlite3.connect(DATABASE)

    query = """
    SELECT 
        s.signal_id,
        s.symbol,
        s.timestamp,
        s.signal_market_cap,
        s.signal_price,
        -- Outcomes
        o.peak_market_cap,
        o.max_return,
        o.time_to_peak,
        o.rugged,
        o.returned_2x,
        o.returned_5x,
        o.returned_10x,
        -- Execution (using actual trades if exists)
        t.entry_price as s6_entry_price,
        t.entry_market_cap as s6_entry_mc,
        t.pnl_percent as s6_pnl_percent,
        -- Intelligence at T0
        i.buy_sell_ratio,
        i.mc_velocity,
        i.volume_velocity,
        i.sentiment_strength,
        -- First snapshot for liquidity
        sn.liquidity as t0_liquidity,
        sn.volume as t0_volume
    FROM signals s
    LEFT JOIN outcomes o ON s.signal_id = o.signal_id
    LEFT JOIN trades t ON s.signal_id = t.signal_id
    LEFT JOIN intelligence i ON s.signal_id = i.signal_id AND i.collection_index = 0
    LEFT JOIN (
        SELECT signal_id, MIN(id) as first_id
        FROM snapshots
        GROUP BY signal_id
    ) sn_min ON s.signal_id = sn_min.signal_id
    LEFT JOIN snapshots sn ON sn_min.first_id = sn.id
    ORDER BY s.timestamp ASC
    """

    print("Executing query...")
    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"Extracted {len(df)} records.")

    # Feature Engineering
    df['t0_liquidity'] = df['t0_liquidity'].fillna(1.0)
    df['t0_volume'] = df['t0_volume'].fillna(1.0)
    df['signal_market_cap'] = df['signal_market_cap'].fillna(1.0).replace(0, 1.0)
    
    df['liq_to_mc'] = df['t0_liquidity'] / df['signal_market_cap']
    df['vol_to_mc'] = df['t0_volume'] / df['signal_market_cap']

    # Splitting chronologically (60-20-20)
    n = len(df)
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)

    df['split'] = 'train'
    if val_end > train_end:
        df.iloc[train_end:val_end, df.columns.get_loc('split')] = 'val'
        df.iloc[val_end:, df.columns.get_loc('split')] = 'test'

    out_file = os.path.join(os.path.dirname(__file__), "s7_dataset.csv")
    df.to_csv(out_file, index=False)
    print(f"Saved dataset to {out_file}")
    
    print(df['split'].value_counts())

if __name__ == "__main__":
    build_dataset()
