import sqlite3

def purge_exam_data(profiles):
    conn = sqlite3.connect('result_finder.db')
    for profile in profiles:
        er = conn.execute("DELETE FROM exam_results WHERE profile_name=?", (profile,)).rowcount
        sg = conn.execute("DELETE FROM subject_grades WHERE profile_name=?", (profile,)).rowcount
        print(f"[{profile}] Deleted {er} exam results, {sg} subject grades")
        
        # Verify students are untouched
        students = conn.execute("SELECT COUNT(*) FROM students WHERE profile_name=?", (profile,)).fetchone()[0]
        print(f"  -> students table still has {students} rows (untouched)")
    conn.commit()
    conn.close()
    print("\nDone. Student profiles, names, and reg numbers are fully preserved.")

if __name__ == "__main__":
    purge_exam_data(['eee 09', 'civil 09'])
