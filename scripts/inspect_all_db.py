import sqlite3
import json

conn = sqlite3.connect("result_finder.db")

print("Profiles and count of students in DB:")
cursor = conn.execute("SELECT profile_name, COUNT(*), MIN(reg_no), MAX(reg_no) FROM students GROUP BY profile_name")
for row in cursor:
    print(f"  Profile: {row[0]} | Count: {row[1]} | Min Reg: {row[2]} | Max Reg: {row[3]}")
    
# Let's inspect some other 10-digit registration numbers in civil 10, eee 10, eee 11, civil 11
print("\nChecking any students from NITER or Mymensingh in DB:")
cursor2 = conn.execute("""
    SELECT profile_name, reg_no, name FROM students 
    WHERE reg_no >= 2022000000 
    LIMIT 20
""")
for row in cursor2:
    # We can do a quick probe if we want to check their college name
    print(f"  {row[0]} | {row[1]} | {row[2]}")
