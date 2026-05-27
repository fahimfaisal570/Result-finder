import sys
sys.path.insert(0, '.')
import cli_scraper as cs
import json

print("Fetching sessions...")
progs, sessions = cs.fetch_programs_and_sessions()
print("SESSIONS:")
for k, v in sessions.items():
    print(f"  {k}: {v}")

print("\nFetching exams for CSE (program_id = '14')...")
exams = cs.fetch_exams('14')
print(f"Total exams found: {len(exams)}")
for k, v in exams.items():
    print(f"  {k}: {v}")

# Save the latest exams list to cse_exams.json
with open("cse_exams.json", "w", encoding="utf-8") as f:
    json.dump(exams, f, indent=4, ensure_ascii=False)
print("\nSaved cse_exams.json")
