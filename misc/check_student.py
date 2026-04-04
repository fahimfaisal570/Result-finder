import sqlite3
import json

def check_student_json(profile, reg_no):
    conn = sqlite3.connect('result_finder.db')
    cursor = conn.execute("SELECT raw_json FROM exam_results WHERE profile_name=? AND reg_no=?", (profile, reg_no))
    row = cursor.fetchone()
    if row:
        data = json.loads(row[0])
        print(f"--- Student {reg_no} ({profile}) ---")
        print(f"Overall Result: {data.get('Overall Result', '-')}")
        print(f"GPA: {data.get('GPA', '-')}")
        print("Subjects Scraped:")
        for s in data.get('Subjects', []):
            print(f"  {s['code']}: {s['gp']} ({s['grade']})")
            
        # Also check if the raw HTML snippet is still in the raw_json (if we saved it)
        # We don't save raw HTML in raw_json currently, only the dict.
    else:
        print(f"No data for {profile} reg {reg_no}")
    conn.close()

if __name__ == "__main__":
    check_student_json('civil 09', 1038)
    check_student_json('eee 09', 974)
