import sqlite3
import json

def dump_raw_json():
    conn = sqlite3.connect('result_finder.db')
    cursor = conn.execute("SELECT reg_no, raw_json FROM exam_results WHERE profile_name='eee 09' LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"Registration No: {row[0]}")
        data = json.loads(row[1])
        print(json.dumps(data, indent=4))
    else:
        print("No results found for eee 09.")
    conn.close()

if __name__ == "__main__":
    dump_raw_json()
