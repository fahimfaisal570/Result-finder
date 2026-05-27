import sqlite3
import json

conn = sqlite3.connect("result_finder.db")

print("=== CSE 10 STUDENTS IN DB ===")
cursor_10 = conn.execute("SELECT reg_no, name, sess_id FROM students WHERE profile_name='cse 10' ORDER BY reg_no")
for row in cursor_10:
    print(f"Reg: {row[0]}, Name: {row[1]}, Session: {row[2]}")

print("\n=== CSE 09 STUDENTS IN DB ===")
cursor_09 = conn.execute("SELECT reg_no, name, sess_id FROM students WHERE profile_name='cse 09' ORDER BY reg_no")
for row in cursor_09:
    print(f"Reg: {row[0]}, Name: {row[1]}, Session: {row[2]}")

print("\n=== COGNATE EXAM RESULTS RAW_JSON SAMPLE (CSE 09) ===")
row_09 = conn.execute("SELECT reg_no, raw_json FROM exam_results WHERE profile_name='cse 09' LIMIT 1").fetchone()
if row_09:
    print(f"Reg: {row_09[0]}")
    try:
        data = json.loads(row_09[1])
        print("Keys in raw_json:", data.keys())
        print("College:", data.get("College"))
        print("Name:", data.get("Name"))
    except Exception as e:
        print("Error parsing:", e)
        print("Raw text snippet:", row_09[1][:300])
