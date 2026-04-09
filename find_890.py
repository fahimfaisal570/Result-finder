import cli_scraper
import json

def find_890():
    print("--- Searching for 890 (Civil 09, Sess 22) ---")
    exams = cli_scraper.fetch_exams(12)
    # Try the first 50 exams
    for eid, ename in list(exams.items())[:50]:
        res, is_any = cli_scraper.fetch_student_result(890, 12, 22, eid)
        if res and isinstance(res, dict) and res.get('GPA') != '-':
            print(f"FOUND! Exam: {ename} ({eid})")
            print(f"Name: {res.get('Name')}")
            print(f"Subjects: {len(res.get('Subjects', []))}")
            break
        elif res and isinstance(res, dict):
             # Found something but no GPA? Maybe just generic info
             print(f"Found Record (No GPA) in Exam {eid}: Name={res.get('Name')}")

if __name__ == "__main__":
    find_890()
