import sqlite3, json

def check_json(profile_name, reg_no):
    conn = sqlite3.connect('result_finder.db')
    row = conn.execute("SELECT raw_json FROM exam_results WHERE profile_name=? AND reg_no=?", (profile_name, reg_no)).fetchone()
    if row:
        data = json.loads(row[0])
        print(f"--- JSON for {profile_name} student {reg_no} ---")
        print(json.dumps(data, indent=2))
    else:
        print(f"NOT FOUND: {profile_name} {reg_no}")
    conn.close()

if __name__ == "__main__":
    check_json('eee 09', 951)
    check_json('cse 09', 956) # Student shown with '0' in first screenshot
