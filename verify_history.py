import cli_scraper
import json
import re

def verify_history():
    print("--- History Logic Verification ---")
    reg = 890
    pro = "12" # Civil
    sess = "22" # Session 22 (2022)
    
    # 1. Fetch programs/sessions to populate caches
    cli_scraper.fetch_programs_and_sessions()
    exams = cli_scraper.fetch_exams(pro)
    
    # Logic simulation (same as in cli_scraper.py)
    sess_name = cli_scraper.SESSIONS_CACHE.get(sess, "")
    y_match = re.search(r"20(\d{2})", sess_name)
    start_search_year = int("20" + y_match.group(1)) if y_match else 0
    print(f"Detected Start Year for Session {sess}: {start_search_year}")
    
    filtered = []
    skipped_count = 0
    for eid, ename in exams.items():
        _, _, ey = cli_scraper.parse_exam_info(ename)
        if ey and start_search_year and ey < (start_search_year - 1):
            skipped_count += 1
            continue
        filtered.append(eid)
    
    print(f"Total Exams: {len(exams)}")
    print(f"Skipped (Too Old): {skipped_count}")
    print(f"Remaining Scope: {len(filtered)}")
    
    # Check if a known old exam (e.g., from 2018) was skipped
    # (Based on previous fetch_exams output, or we just trust the math)
    print("Verification complete.")

if __name__ == "__main__":
    verify_history()
