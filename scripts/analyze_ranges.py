import sqlite3

conn = sqlite3.connect("result_finder.db")

profiles = ["cse 11", "eee 11", "civil 11"]

for p in profiles:
    print(f"=== PROFILE: {p} ===")
    cursor = conn.execute("SELECT reg_no FROM students WHERE profile_name = ? AND reg_no >= 2023000000", (p,))
    regs = [str(r[0]) for r in cursor.fetchall()]
    
    suffixes = [int(r[5:]) for r in regs]
    if suffixes:
        print(f"  Total Regular Students: {len(suffixes)}")
        print(f"  Min Suffix: {min(suffixes)}")
        print(f"  Max Suffix: {max(suffixes)}")
        print(f"  Actual Suffix Range: {min(suffixes)} to {max(suffixes)}")
        print(f"  All Suffixes (sorted): {sorted(suffixes)}")
