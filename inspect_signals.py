import sqlite3
import json
from config import DATABASE

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM signals WHERE symbol LIKE '%Jibanyan%' OR symbol LIKE '%DANOTHY%' OR symbol LIKE '%JIBANYAN%' OR symbol LIKE '%danothy%'")
signals = [dict(r) for r in cur.fetchall()]

if not signals:
    print("No matching signals by symbol found. Listing all signals:")
    cur.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 20")
    for r in cur.fetchall():
        row_d = dict(r)
        print(row_d.get('signal_id'), row_d.get('symbol'))
        if 'Jibanyan' in str(row_d) or 'DANOTHY' in str(row_d):
            signals.append(row_d)

print("=== SIGNALS FOUND ===")
for s in signals:
    print(f"Signal ID: {s.get('signal_id')}, Symbol: {s.get('symbol')}, Name: {s.get('name')}, Contract: {s.get('contract')}, Timestamp: {s.get('timestamp')}")

for s in signals:
    sid = s.get('signal_id')
    cur.execute("SELECT * FROM intelligence WHERE signal_id=?", (sid,))
    intel_rows = [dict(r) for r in cur.fetchall()]
    print(f"\n=== INTELLIGENCE ROWS FOR {s.get('symbol')} ({sid}) ===")
    print(f"Total intel rows: {len(intel_rows)}")
    for idx, row in enumerate(intel_rows):
        print(f"\n--- Row {idx} (index {row.get('collection_index')}, {row.get('collection_minutes')}m, collected_at: {row.get('collected_at')}) ---")
        for k, v in row.items():
            print(f"  {k}: {v}")

conn.close()
