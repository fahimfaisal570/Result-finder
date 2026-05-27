import sqlite3

conn = sqlite3.connect("result_finder.db")
print("PROFILES:")
for row in conn.execute("SELECT name, pro_id, sess_id FROM profiles ORDER BY name"):
    print(row)

print("\nSTUDENT COUNTS PER PROFILE:")
for row in conn.execute("SELECT profile_name, COUNT(*) FROM students GROUP BY profile_name ORDER BY profile_name"):
    print(row)




