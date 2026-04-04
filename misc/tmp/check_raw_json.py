import sys
import os
sys.path.insert(0, os.getcwd())
import database as db
import json

def check_one_student():
    profile_name = "eee 09"
    exam_id = "1234"
    conn = db.get_connection()
    row = conn.execute("SELECT reg_no, raw_json FROM exam_results WHERE profile_name=? AND exam_id=? LIMIT 1", (profile_name, exam_id)).fetchone()
    if row:
        reg_no, raw_json_str = row
        print(f"--- Raw JSON for Student {reg_no} ---")
        try:
            data = json.loads(raw_json_str)
            print(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            print(raw_json_str)
    else:
        print("No results found.")

if __name__ == "__main__":
    check_one_student()
