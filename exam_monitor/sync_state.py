import urllib.request
import re
import json
import os

PROGRAMS = ["12", "13", "14"]
KNOWN_EXAMS_FILE = "exam_monitor/known_exams.json"

def fetch_all_ids(pid):
    url = f"https://ducmc.du.ac.bd/ajax/get_program_by_exam.php?program_id={pid}&pedata=99"
    try:
        html = urllib.request.urlopen(url).read().decode('utf-8')
        return re.findall(r'<option[^>]+value=["\'](\d+)["\'][^>]*>', html)
    except:
        return []

new_state = {}
for pid in PROGRAMS:
    ids = fetch_all_ids(pid)
    new_state[pid] = ids
    print(f"Dept {pid}: Found {len(ids)} exams.")

with open(KNOWN_EXAMS_FILE, "w") as f:
    json.dump(new_state, f, indent=4)
print("Synchronized known_exams.json with current portal state.")
