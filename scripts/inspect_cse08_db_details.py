import sqlite3
import json
from collections import Counter

conn = sqlite3.connect("result_finder.db")
cursor = conn.execute("SELECT reg_no, sess_id, name FROM students WHERE profile_name='cse 08'")
rows = cursor.fetchall()
print(f"Total students in cse 08: {len(rows)}")

colleges = Counter()
for row in rows:
    cursor_res = conn.execute("SELECT raw_json FROM exam_results WHERE profile_name='cse 08' AND reg_no=?", (row[0],))
    res_row = cursor_res.fetchone()
    if res_row:
        data = json.loads(res_row[0])
        col = data.get("College", "Unknown")
        colleges[col] += 1
    else:
        colleges["No Exam Result Row"] += 1

print("\nColleges in cse 08:")
for c, count in colleges.items():
    print(f"  {c}: {count}")
