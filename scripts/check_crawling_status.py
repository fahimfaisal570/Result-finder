import os
import json
import time

json_path = "found_results_cse11_exam1375.json"
if os.path.exists(json_path):
    mtime = os.path.getmtime(json_path)
    print(f"File: {json_path}")
    print(f"Last Modified: {time.ctime(mtime)}")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            students = json.load(f)
        print(f"Total students in file: {len(students)}")
        # breakdown sessions
        from collections import Counter
        sessions = Counter(s.get("_sess_id", "24") for s in students)
        colleges = Counter(s.get("College", "Unknown") for s in students)
        print("\nSessions:")
        for s, cnt in sorted(sessions.items()):
            print(f"  Session {s}: {cnt}")
        print("\nColleges:")
        for c, cnt in sorted(colleges.items()):
            print(f"  {c}: {cnt}")
    except Exception as e:
        print(f"Error reading JSON: {e}")
else:
    print(f"File {json_path} does not exist!")
