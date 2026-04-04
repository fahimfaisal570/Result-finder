import sqlite3, json, os

def repair():
    db_path = 'result_finder.db'
    map_path = 'credit_mapping.json'
    
    if not os.path.exists(map_path):
        print("Mapping file not found!")
        return

    with open(map_path, 'r') as f:
        credit_map = json.load(f)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get all subject grades
    subjects = cur.execute("SELECT rowid, subject_code FROM subject_grades").fetchall()
    
    updated_count = 0
    for rowid, code in subjects:
        clean_code = str(code).strip().upper().replace(' ', '-')
        if clean_code in credit_map:
            new_credit = credit_map[clean_code]
            cur.execute("UPDATE subject_grades SET credit_hours = ? WHERE rowid = ?", (new_credit, rowid))
            updated_count += 1
            
    conn.commit()
    conn.close()
    print(f"[*] Successfully repaired {updated_count} subject records with accurate credit hours.")

if __name__ == "__main__":
    repair()
