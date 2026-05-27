import json

with open("found_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

# Group by College for session 21
col_groups = {}
for r in results:
    if r.get("_sess_id") == "21":
        col = r.get("College", "Unknown")
        reg = int(r["Registration No"])
        if col not in col_groups:
            col_groups[col] = []
        col_groups[col].append(reg)

print("CSE 08 (Session 21) Registration Distribution by College:")
for col, regs in col_groups.items():
    regs.sort()
    print(f"\nCollege: {col}")
    print(f"  Count: {len(regs)}")
    print(f"  Min Reg: {regs[0]}")
    print(f"  Max Reg: {regs[-1]}")
    print(f"  All Regs: {regs}")
