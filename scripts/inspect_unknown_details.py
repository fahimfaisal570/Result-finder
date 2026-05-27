import sqlite3
import json

conn = sqlite3.connect("result_finder.db")

for prof in ["eee 11", "civil 11"]:
    print(f"\n=== Profile: {prof} ===")
    cursor = conn.execute("SELECT reg_no, raw_json FROM exam_results WHERE profile_name=? LIMIT 1", (prof,))
    row = cursor.fetchone()
    if row:
        print(f"Reg: {row[0]}")
        try:
            data = json.loads(row[1])
            print(json.dumps(data, indent=2))
        except:
            print(row[1])
    else:
        print("No row found")
