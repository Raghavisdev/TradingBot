import sqlite3
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from config import DATABASE

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM signals WHERE symbol IN ('Jibanyan', 'DANOTHY')")
rows = [dict(r) for r in cur.fetchall()]

for r in rows:
    print(f"=== SIGNAL: {r.get('symbol')} ===")
    for k, v in r.items():
        print(f"  {k}: {repr(v)}")

conn.close()
