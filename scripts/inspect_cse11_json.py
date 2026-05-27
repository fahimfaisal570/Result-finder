import sqlite3
import json
from collections import Counter

conn = sqlite3.connect("result_finder.db")

print("Checking cse 11 students in DB exam_results:")
cursor = conn.execute("""
    SELECT reg_no, exam_id, raw_json, sess_id
    FROM exam_results
    WHERE profile_name = 'cse 11'
""")

rows = cursor.fetchall()
print(f"Total exam_results in DB for cse 11: {len(rows)}")

colleges = Counter()
sessions = Counter()
coll_sess = Counter()

for row in rows:
    reg = row[0]
    exam_id = row[1]
    raw_str = row[2]
    sess = row[3]
    
    try:
        data = json.loads(raw_str)
        col = data.get("College", "Unknown")
    except Exception as e:
        col = "Error Parsing JSON"
        
    colleges[col] += 1
    sessions[sess] += 1
    coll_sess[(col, sess)] += 1

print("\nBreakdown by College in DB exam_results:")
for c, count in sorted(colleges.items()):
    print(f"  {c}: {count}")

print("\nBreakdown by Session in DB exam_results:")
for s, count in sorted(sessions.items()):
    print(f"  Session {s}: {count}")

print("\nBreakdown by College + Session in DB exam_results:")
for (c, s), count in sorted(coll_sess.items()):
    print(f"  {c} | Session {s}: {count}")
