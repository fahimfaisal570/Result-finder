import json
from collections import defaultdict

with open("found_results_cse11_exam1375.json", "r", encoding="utf-8") as f:
    students = json.load(f)

print(f"Total students: {len(students)}")

by_college = defaultdict(list)
for s in students:
    by_college[s.get("College", "Unknown")].append(s)

for col, list_studs in by_college.items():
    print(f"\nCollege: {col} | Total: {len(list_studs)}")
    by_sess = defaultdict(list)
    for s in list_studs:
        by_sess[s.get("_sess_id", "24")].append(s)
        
    for sess, s_list in sorted(by_sess.items()):
        print(f"  Session {sess} | Count: {len(s_list)}")
        suffixes = []
        for s in s_list:
            reg = str(s['Registration No'])
            if len(reg) == 10:
                suffix = int(reg[5:])
                suffixes.append(suffix)
            else:
                suffixes.append(int(reg) if reg.isdigit() else reg)
                
        num_suffixes = [sf for sf in suffixes if isinstance(sf, int)]
        str_suffixes = [sf for sf in suffixes if isinstance(sf, str)]
        
        if num_suffixes:
            sorted_sf = sorted(num_suffixes)
            print(f"    Suffixes - Min: {min(sorted_sf)} | Max: {max(sorted_sf)}")
            if len(sorted_sf) <= 15:
                print(f"    All: {sorted_sf}")
            else:
                print(f"    First 5 Suffixes: {sorted_sf[:5]}")
                print(f"    Last 5 Suffixes: {sorted_sf[-5:]}")
                # check gaps
                gaps = []
                for i in range(len(sorted_sf) - 1):
                    if sorted_sf[i+1] - sorted_sf[i] > 1:
                        gaps.append((sorted_sf[i], sorted_sf[i+1]))
                if gaps:
                    print(f"    Detected Suffix gaps ({len(gaps)} total): {gaps[:10]}")
                else:
                    print("    Zero Suffix gaps!")
        if str_suffixes:
            print(f"    Other: {sorted(str_suffixes)}")
