import cli_scraper
import json

def verify():
    print("--- Verification Start ---")
    
    # 1. Test Student 890 (Civil 09)
    # Reg: 890, Pro: 12, Sess: 22
    # Exam identification: We'll try a few recent ones
    exams = cli_scraper.fetch_exams(12)
    # Filter for exams that likely match 'Main' or something standard
    # For Civil 09, let's try to find an exam that matches their level (e.g. 4th year)
    
    target_890 = (890, "12", "22")
    target_shanto = (2022654793, "12", "23")
    
    # Probable exams for Civil 09 (Sess 22) - 2nd/3rd year exams
    exams_890 = ["1400", "1372", "1244", "1208", "1192", "1110"]
    # Probable exams for Civil 10 (Sess 23) - 1st/2nd year exams
    exams_shanto = ["1758", "1742", "1604", "1588", "1434", "1405"]

    print(f"Testing Student 890 (Civil 09)...")
    for eid in exams_890:
        ename = exams.get(eid, "Unknown")
        print(f"Checking Exam: {ename} ({eid})")
        res, is_any = cli_scraper.fetch_student_result(target_890[0], target_890[1], target_890[2], eid)
        if res and isinstance(res, dict):
            print(f"  SUCCESS! Name: {res.get('Name')}, Overall: {res.get('Overall Result')}")
            print(f"  Subjects captured: {len(res.get('Subjects', []))}")
            break

    print("\nTesting Shanto (Civil 10)...")
    for eid in exams_shanto:
        ename = exams.get(eid, "Unknown")
        print(f"Checking Exam: {ename} ({eid})")
        res, is_any = cli_scraper.fetch_student_result(target_shanto[0], target_shanto[1], target_shanto[2], eid)
        if res and isinstance(res, dict):
            print(f"  SUCCESS! Name: {res.get('Name')}, Overall: {res.get('Overall Result')}")
            print(f"  Subjects captured: {len(res.get('Subjects', []))}")
            for sub in res.get('Subjects', []):
                print(f"    - {sub['code']}: {sub['name']} ({sub['grade']})")
            break

    print("--- Verification End ---")

if __name__ == "__main__":
    verify()
