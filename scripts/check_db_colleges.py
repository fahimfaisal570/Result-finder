import sqlite3
import json

conn = sqlite3.connect("result_finder.db")

cursor = conn.execute("SELECT profile_name, raw_json FROM exam_results WHERE raw_json IS NOT NULL")
col_by_profile = {}
for row in cursor:
    pname, rjson = row
    try:
        data = json.loads(rjson)
        col = data.get("College") or data.get("college_name")
        if col:
            if pname not in col_by_profile:
                col_by_profile[pname] = set()
            col_by_profile[pname].add(col)
    except:
        pass

print("Colleges represented in each profile in the DB:")
for pname, cols in col_by_profile.items():
    print(f"  Profile: {pname} -> {list(cols)}")
