import sys
import os
sys.path.insert(0, os.getcwd())
import database as db

def check_exam():
    profile = "cse 09"
    id1 = "1298"
    id2 = "1699"
    conn = db.get_connection()
    
    print(f"--- Checking {profile} ---")
    
    for eid in [id1, id2]:
        row = conn.execute("SELECT exam_name FROM exam_results WHERE profile_name=? AND exam_id=? LIMIT 1", (profile, eid)).fetchone()
        name = row[0] if row else "None"
        c1 = conn.execute("SELECT COUNT(*) FROM exam_results WHERE profile_name=? AND exam_id=?", (profile, eid)).fetchone()[0]
        c2 = conn.execute("SELECT COUNT(*) FROM scan_log WHERE profile_name=? AND exam_id=?", (profile, eid)).fetchone()[0]
        print(f"Exam ID: {eid} | Name: {name}")
        print(f"  Results count: {c1}")
        print(f"  ScanLog count: {c2}")
        
    # Check all in scan_log for this profile
    print("\nAll in scan_log for this profile:")
    rows = conn.execute("SELECT exam_id FROM scan_log WHERE profile_name=?", (profile,)).fetchall()
    print([r[0] for r in rows])
    
    # Check what get_exams_for_profile returns
    print("\nget_exams_for_profile returns:")
    exams = db.get_exams_for_profile(profile)
    for e in exams:
        print(e)

if __name__ == "__main__":
    check_exam()
