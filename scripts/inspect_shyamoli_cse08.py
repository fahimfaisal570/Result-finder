import json
from collections import defaultdict

with open("found_results.json", "r", encoding="utf-8") as f:
    students = json.load(f)

by_college = defaultdict(list)
for s in students:
    by_college[s.get("College", "Unknown")].append(s)

for col, s_list in sorted(by_college.items()):
    print(f"\nCollege: {col} | Count: {len(s_list)}")
    regs = sorted([s['Registration No'] for s in s_list])
    print(f"  Min: {min(regs)} | Max: {max(regs)}")
    print(f"  All: {regs}")
