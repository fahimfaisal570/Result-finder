import sqlite3

def purge_corrupted_data():
    conn = sqlite3.connect('result_finder.db')
    try:
        # 1. Delete all subject grades for affected batches
        cursor = conn.execute("DELETE FROM subject_grades WHERE profile_name IN ('eee 09', 'civil 09')")
        grades_deleted = cursor.rowcount
        
        # 2. Delete exam result metadata
        cursor = conn.execute("DELETE FROM exam_results WHERE profile_name IN ('eee 09', 'civil 09')")
        exams_deleted = cursor.rowcount
        
        conn.commit()
        print(f"[*] Success: Purged {grades_deleted} subject grades and {exams_deleted} exam records.")
        print("[*] Student profiles (names/reg nos) remain safe.")
        
    except Exception as e:
        print(f"[!] Error during purge: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    purge_corrupted_data()
