import sqlite3

conn = sqlite3.connect("result_finder.db")

for profile in ["cse 10", "eee 10", "civil 10"]:
    print(f"\n=== Profile: {profile} ===")
    cursor = conn.execute(
        "SELECT reg_no, name FROM students WHERE profile_name = ? AND reg_no >= 2022000000 ORDER BY reg_no",
        (profile,)
    )
    rows = cursor.fetchall()
    print(f"Total 10-digit students in DB: {len(rows)}")
    if not rows:
        continue
    suffixes = [int(str(r[0])[5:]) for r in rows]
    print(f"Suffix range: {min(suffixes)} to {max(suffixes)}")
    # Print distinct 100s blocks
    blocks = sorted(list(set(s // 100 for s in suffixes)))
    print("Blocks (suffix // 100):", blocks)
    # Print some samples
    for b in blocks:
        sample = [s for s in suffixes if s // 100 == b]
        print(f"  Block {b}00: Count {len(sample)}, Min {min(sample)}, Max {max(sample)}")
