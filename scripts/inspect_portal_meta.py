import sqlite3
import json

conn = sqlite3.connect("result_finder.db")
cursor = conn.execute("SELECT value FROM meta_cache WHERE key='portal_meta'")
row = cursor.fetchone()
if row:
    data = json.loads(row[0])
    print("PROGRAMS:")
    for k, v in sorted(data.get("programs", {}).items()):
        print(f"  {k}: {v}")
    print("\nSESSIONS:")
    for k, v in sorted(data.get("sessions", {}).items()):
        print(f"  {k}: {v}")
else:
    print("No portal_meta found in DB")
