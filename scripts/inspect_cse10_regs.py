import sqlite3

conn = sqlite3.connect("result_finder.db")

print("CSE 10 Registrations:")
cursor = conn.execute("SELECT reg_no, name FROM students WHERE profile_name='cse 10' ORDER BY reg_no")
for row in cursor.fetchall():
    print(f"  Reg: {row[0]} | Name: {row[1]}")

print("\nEEE 10 Registrations:")
cursor = conn.execute("SELECT reg_no, name FROM students WHERE profile_name='eee 10' ORDER BY reg_no")
for row in cursor.fetchall()[:15]:
    print(f"  Reg: {row[0]} | Name: {row[1]}")
