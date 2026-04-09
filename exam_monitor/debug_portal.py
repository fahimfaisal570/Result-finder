import urllib.request
import re

PROGRAMS = {
    "12": "Civil",
    "13": "EEE",
    "14": "CSE"
}

def debug_fetch(pid):
    url = f"https://ducmc.du.ac.bd/ajax/get_program_by_exam.php?program_id={pid}&pedata=99"
    try:
        html = urllib.request.urlopen(url).read().decode('utf-8')
        matches = re.findall(r'<option[^>]+value=["\'](\d+)["\'][^>]*>(.*?)</option>', html)
        print(f"\n--- {PROGRAMS[pid]} (Top 5) ---")
        for eid, name in matches[:5]:
            name_lower = name.lower()
            exclusions = ["retake", "improvement", "special", "clearance", "backlog", "junior", "short", "carry"]
            excluded = any(ex in name_lower for ex in exclusions)
            status = "[SKIP - EXCLUDED]" if excluded else "[VALID MAIN]"
            print(f"{eid}: {name} {status}")
    except Exception as e:
        print(f"Error fetching {pid}: {e}")

for pid in PROGRAMS:
    debug_fetch(pid)
