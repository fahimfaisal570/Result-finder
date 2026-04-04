import sqlite3

def check_failed_subjects():
    conn = sqlite3.connect('result_finder.db')
    
    batches = [('eee 09', '1234'), ('civil 09', '1243')] # IDs from screenshots
    
    for profile, exam_id in batches:
        print(f"\n--- Checking {profile} (Exam {exam_id}) ---")
        
        # Total counts
        total_results = conn.execute("SELECT COUNT(*) FROM exam_results WHERE profile_name=? AND exam_id=?", (profile, exam_id)).fetchone()[0]
        total_grades = conn.execute("SELECT COUNT(*) FROM subject_grades WHERE profile_name=? AND exam_id=?", (profile, exam_id)).fetchone()[0]
        
        # Failed count
        failed_grades = conn.execute("SELECT COUNT(*) FROM subject_grades WHERE profile_name=? AND exam_id=? AND grade_point < 2.0", (profile, exam_id)).fetchone()[0]
        
        print(f"Total students in exam: {total_results}")
        print(f"Total subject grades: {total_grades}")
        print(f"Failed subject grades (GP < 2.0): {failed_grades}")
        
        if failed_grades == 0 and total_results > 0:
            print("[!] WARNING: No failed grades found. This confirms the user's report.")
            
            # Sample a few students to see if they have any grades at all
            sample = conn.execute("SELECT reg_no, COUNT(*) FROM subject_grades WHERE profile_name=? AND exam_id=? GROUP BY reg_no LIMIT 5", (profile, exam_id)).fetchall()
            print(f"Sample student grade counts: {sample}")

    conn.close()

if __name__ == "__main__":
    check_failed_subjects()
