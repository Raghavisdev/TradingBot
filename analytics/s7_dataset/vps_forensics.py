import sqlite3

def run_forensics():
    db = "database/trading.db"
    print(f"Connecting to {db}...")
    try:
        c = sqlite3.connect(db)
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return
        
    c.row_factory = sqlite3.Row

    print("\n==================================================")
    print("4. RUN DIRECT SQL VERSION")
    print("==================================================")
    
    q1 = """
    SELECT COUNT(DISTINCT s.signal_id)
    FROM signals s
    JOIN snapshots sn ON sn.signal_id = s.signal_id
    WHERE CAST(sn.timestamp AS REAL) <= CAST(s.timestamp AS REAL);
    """
    print("Snapshots <= T0:", c.execute(q1).fetchone()[0])
    
    q2 = """
    SELECT COUNT(DISTINCT s.signal_id)
    FROM signals s
    JOIN intelligence i ON i.signal_id = s.signal_id
    WHERE CAST(i.collected_at AS REAL) <= CAST(s.timestamp AS REAL);
    """
    print("Intelligence <= T0:", c.execute(q2).fetchone()[0])

    print("\n==================================================")
    print("5. INSPECT TYPES")
    print("==================================================")
    
    for row in c.execute("SELECT typeof(timestamp) as t, COUNT(*) as c FROM signals GROUP BY typeof(timestamp)"):
        print(f"signals.timestamp type: {row['t']} (count: {row['c']})")
        
    for row in c.execute("SELECT typeof(timestamp) as t, COUNT(*) as c FROM snapshots GROUP BY typeof(timestamp)"):
        print(f"snapshots.timestamp type: {row['t']} (count: {row['c']})")
        
    for row in c.execute("SELECT typeof(collected_at) as t, COUNT(*) as c FROM intelligence GROUP BY typeof(collected_at)"):
        print(f"intelligence.collected_at type: {row['t']} (count: {row['c']})")

    print("\n==================================================")
    print("6. INSPECT ACTUAL VALUES (First 5 signals)")
    print("==================================================")
    
    signals = c.execute("SELECT signal_id, timestamp FROM signals LIMIT 5").fetchall()
    for s in signals:
        sig_id = s['signal_id']
        print(f"\nSignal ID: {sig_id} | signals.timestamp: {repr(s['timestamp'])}")
        
        snaps = c.execute("SELECT timestamp FROM snapshots WHERE signal_id = ? ORDER BY CAST(timestamp AS REAL) ASC LIMIT 3", (sig_id,)).fetchall()
        print(f"  First 3 Snapshots: {[repr(sn['timestamp']) for sn in snaps]}")
        
        intels = c.execute("SELECT collected_at FROM intelligence WHERE signal_id = ? ORDER BY CAST(collected_at AS REAL) ASC LIMIT 3", (sig_id,)).fetchall()
        print(f"  First 3 Intelligence: {[repr(i['collected_at']) for i in intels]}")

    print("\n==================================================")
    print("7. CHECK SIGNAL_ID JOIN")
    print("==================================================")
    
    print("Distinct signals.signal_id:", c.execute("SELECT COUNT(DISTINCT signal_id) FROM signals").fetchone()[0])
    print("Distinct snapshots.signal_id:", c.execute("SELECT COUNT(DISTINCT signal_id) FROM snapshots").fetchone()[0])
    print("Distinct intelligence.signal_id:", c.execute("SELECT COUNT(DISTINCT signal_id) FROM intelligence").fetchone()[0])
    
    print("Signals JOIN Snapshots:", c.execute("SELECT COUNT(DISTINCT s.signal_id) FROM signals s JOIN snapshots sn ON sn.signal_id = s.signal_id").fetchone()[0])
    print("Signals JOIN Intelligence:", c.execute("SELECT COUNT(DISTINCT s.signal_id) FROM signals s JOIN intelligence i ON i.signal_id = s.signal_id").fetchone()[0])

    print("\n==================================================")
    print("8. FIND THE FIRST DISAGREEMENT")
    print("==================================================")
    
    q_disagreement = """
    SELECT s.signal_id, s.timestamp as s_ts, sn.timestamp as sn_ts
    FROM signals s
    JOIN snapshots sn ON sn.signal_id = s.signal_id
    WHERE CAST(sn.timestamp AS REAL) <= CAST(s.timestamp AS REAL)
    LIMIT 1;
    """
    row = c.execute(q_disagreement).fetchone()
    if row:
        print(f"Direct SQL matches this snapshot -> Signal: {row['signal_id']}")
        print(f"  signals.timestamp: {repr(row['s_ts'])} | CAST: {float(row['s_ts']) if row['s_ts'] else 0.0}")
        print(f"  snapshots.timestamp: {repr(row['sn_ts'])} | CAST: {float(row['sn_ts']) if row['sn_ts'] else 0.0}")
        print("  Builder query would do: CAST(sn.timestamp AS REAL) <= parse_timestamp(s_ts)")
    
    c.close()

if __name__ == "__main__":
    run_forensics()
