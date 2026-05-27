import sqlite3

conn = sqlite3.connect("result_finder.db")

profiles = ["cse 11", "eee 11", "civil 11"]

for p in profiles:
    print(f"=== PROFILE: {p} ===")
    cursor = conn.execute("SELECT reg_no, sess_id, COUNT(*) FROM students WHERE profile_name = ? GROUP BY sess_id", (p,))
    print(cursor.fetchall())
    
    # Let's print some sample regular students (where sess_id = '24' or reg_no starts with 2023)
    cursor2 = conn.execute("SELECT reg_no, name FROM students WHERE profile_name = ? AND reg_no >= 2023000000 LIMIT 5", (p,))
    print("  Regular samples (2023+):", cursor2.fetchall())
