import urllib.request
import re

PROGRAMS = {
    "12": "Civil",
    "13": "EEE",
    "14": "CSE"
}

def get_latest(pid):
    url = f"https://ducmc.du.ac.bd/ajax/get_program_by_exam.php?program_id={pid}&pedata=99"
    try:
        html = urllib.request.urlopen(url).read().decode('utf-8')
        matches = re.findall(r'<option[^>]+value=["\'](\d+)["\'][^>]*>(.*?)</option>', html)
        # We want Main exams for 09 batch
        for eid, name in matches:
            name_lower = name.lower()
            exclusions = ["retake", "improvement", "special", "clearance", "backlog", "junior", "short", "carry"]
            if not any(ex in name_lower for ex in exclusions) and "batch-09" in name_lower:
                return eid, name
        # Fallback to absolute latest main exam if 09 batch specifically not found in top list
        for eid, name in matches:
            name_lower = name.lower()
            if not any(ex in name_lower for ex in exclusions):
                return eid, name
    except:
        return None, None

for pid, name in PROGRAMS.items():
    eid, ename = get_latest(pid)
    print(f"{name} ({pid}): {eid} -> {ename}")
