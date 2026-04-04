import sqlite3, json

def check():
    conn = sqlite3.connect('result_finder.db')
    
    print("--- Profiles ---")
    profiles = conn.execute("SELECT * FROM profiles").fetchall()
    for p in profiles: print(p)

    print("\n--- Exam Results (cse 09, limit 5) ---")
    res = conn.execute("SELECT reg_no, exam_id, result_status, cgpa FROM exam_results WHERE profile_name='cse 09' LIMIT 5").fetchall()
    for r in res: print(r)

    if res:
        test_reg = res[0][0]
        print(f"\n--- Subject Grades (Reg {test_reg}, cse 09) ---")
        subs = conn.execute("SELECT * FROM subject_grades WHERE profile_name='cse 09' AND reg_no=?", (test_reg,)).fetchall()
        for s in subs: print(s)

    conn.close()

if __name__ == "__main__":
    check()
