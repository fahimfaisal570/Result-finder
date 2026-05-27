import sqlite3
import json
from collections import defaultdict

conn = sqlite3.connect("result_finder.db")

print("Checking ALL registrations in students for sess_id='23' (Batch 10):")
cursor = conn.execute("""
    SELECT profile_name, reg_no, name
    FROM students
    WHERE sess_id = '23'
""")

rows = cursor.fetchall()
print(f"Total entries: {len(rows)}")

profile_ranges = defaultdict(list)
for row in rows:
    prof = row[0]
    reg = str(row[1])
    name = row[2]
    
    if len(reg) == 10:
        suffix = int(reg[5:])
        profile_ranges[prof].append(suffix)
    else:
        profile_ranges[prof].append(int(reg) if reg.isdigit() else reg)

for prof, suffixes in sorted(profile_ranges.items()):
    num_sf = [sf for sf in suffixes if isinstance(sf, int)]
    str_sf = [sf for sf in suffixes if isinstance(sf, str)]
    print(f"\nProfile: {prof} | Count: {len(suffixes)}")
    if num_sf:
        print(f"  Suffixes - Min: {min(num_sf)} | Max: {max(num_sf)}")
        if len(num_sf) > 10:
            print(f"  First 5 Suffixes: {sorted(num_sf)[:5]}")
            print(f"  Last 5 Suffixes: {sorted(num_sf)[-5:]}")
        else:
            print(f"  All Suffixes: {sorted(num_sf)}")
    if str_sf:
        print(f"  Other: {sorted(str_sf)}")
