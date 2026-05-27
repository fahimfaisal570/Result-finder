import sqlite3
import json
from collections import Counter

conn = sqlite3.connect("result_finder.db")

for prof in ["eee 11", "civil 11"]:
    print(f"\n=== Profile: {prof} ===")
    cursor = conn.execute("SELECT reg_no, name FROM students WHERE profile_name=?", (prof,))
    rows = cursor.fetchall()
    print(f"Total students in DB for {prof}: {len(rows)}")
    
    colleges = Counter()
    for row in rows:
        cursor_res = conn.execute("SELECT raw_json FROM exam_results WHERE profile_name=? AND reg_no=?", (prof, row[0]))
        res_row = cursor_res.fetchone()
        if res_row:
            try:
                data = json.loads(res_row[0])
                col = data.get("College", "Unknown")
            except:
                col = "Parsing Error"
            colleges[col] += 1
        else:
            colleges["No Exam Result Row"] += 1
            
    for c, count in sorted(colleges.items()):
        print(f"  {c}: {count}")
