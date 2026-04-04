import sqlite3

def check_failed_subjects():
    conn = sqlite3.connect('result_finder.db')
    
    print("--- Database Audit for Fails ---")
    
    # Check EEE 09
    cursor = conn.execute("""
        SELECT COUNT(*) FROM subject_grades 
        WHERE profile_name = 'eee 09' AND grade_point = 0.0
    """)
    fails_eee = cursor.fetchone()[0]
    
    # Check Civil 09
    cursor = conn.execute("""
        SELECT COUNT(*) FROM subject_grades 
        WHERE profile_name = 'civil 09' AND grade_point = 0.0
    """)
    fails_civil = cursor.fetchone()[0]
    
    # Check Total records
    cursor = conn.execute("SELECT COUNT(*) FROM subject_grades WHERE profile_name = 'eee 09'")
    total_eee = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COUNT(*) FROM subject_grades WHERE profile_name = 'civil 09'")
    total_civil = cursor.fetchone()[0]
    
    print(f"EEE 09: Found {fails_eee} failed subjects (GP 0.0) out of {total_eee} total entries.")
    print(f"Civil 09: Found {fails_civil} failed subjects (GP 0.0) out of {total_civil} total entries.")
    
    # Let's see some example data for someone who has a '-' (missing grade) in the pivot table
    print("\n--- Example Subject Data for Reg 974 (EEE 09) ---")
    cursor = conn.execute("""
        SELECT subject_code, grade_point FROM subject_grades 
        WHERE profile_name = 'eee 09' AND reg_no = 974
    """)
    for r in cursor:
        print(f"  {r[0]}: {r[1]}")
        
    conn.close()

if __name__ == "__main__":
    check_failed_subjects()
