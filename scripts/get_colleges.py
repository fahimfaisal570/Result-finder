import sqlite3
import json

conn = sqlite3.connect("result_finder.db")

print("All unique colleges in the database:")
cursor = conn.execute("SELECT raw_json FROM exam_results WHERE raw_json IS NOT NULL")
colleges = set()
for row in cursor:
    try:
        data = json.loads(row[0])
        col = data.get("College") or data.get("college_name")
        if col:
            colleges.add(col)
    except:
        pass

for c in sorted(colleges):
    print(f"  - {c}")
