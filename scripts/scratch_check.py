import json
from collections import Counter

json_path = "found_results_cse11_exam1375.json"

try:
    with open(json_path, "r", encoding="utf-8") as f:
        students = json.load(f)
    print(f"Total students in {json_path}: {len(students)}")
    
    sessions = Counter()
    colleges = Counter()
    sess_college = Counter()
    
    for s in students:
        sess = s.get("_sess_id", "24") # default is regular 24
        col = s.get("College", "Unknown")
        sessions[sess] += 1
        colleges[col] += 1
        sess_college[(sess, col)] += 1
        
    print("\nBreakdown by Session:")
    for s, count in sorted(sessions.items()):
        print(f"  Session {s}: {count}")
        
    print("\nBreakdown by College:")
    for c, count in sorted(colleges.items()):
        print(f"  {c}: {count}")
        
    print("\nBreakdown by Session + College:")
    for (s, c), count in sorted(sess_college.items()):
        print(f"  Session {s} | {c}: {count}")
except Exception as e:
    print(f"Error: {e}")
