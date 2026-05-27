import json
from collections import Counter

json_path = "found_results.json"

try:
    with open(json_path, "r", encoding="utf-8") as f:
        students = json.load(f)
    print(f"Total students in {json_path}: {len(students)}")
    
    colleges = Counter()
    sessions = Counter()
    for s in students:
        colleges[s.get("College", "Unknown")] += 1
        sessions[s.get("_sess_id", "Unknown")] += 1
        
    print("\nBreakdown by College:")
    for c, count in sorted(colleges.items()):
        print(f"  {c}: {count}")
        
    print("\nBreakdown by Session:")
    for ss, count in sorted(sessions.items()):
        print(f"  Session {ss}: {count}")
        
    if students:
        print("\nSample Student:")
        print(json.dumps(students[0], indent=2))
except Exception as e:
    print(f"Error: {e}")
