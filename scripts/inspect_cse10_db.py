import sqlite3
import json

conn = sqlite3.connect("result_finder.db")
cursor = conn.execute("SELECT reg_no, raw_json FROM exam_results WHERE profile_name='cse 10' LIMIT 1")
row = cursor.fetchone()
if row:
    print(f"Reg: {row[0]}")
    try:
        data = json.loads(row[1])
        print(json.dumps(data, indent=2))
    except:
        print(row[1])
else:
    print("No rows found")
