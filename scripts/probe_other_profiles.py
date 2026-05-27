import sqlite3
import sys
sys.path.insert(0, '.')
import cli_scraper as cs
import re

conn = sqlite3.connect("result_finder.db")

profiles = [("eee 11", "1368", "13"), ("civil 11", "1381", "12")]

for p, exam_id, pro_id in profiles:
    print(f"\n=== PROFILE: {p} ===")
    cursor = conn.execute("SELECT reg_no, name FROM students WHERE profile_name = ? AND reg_no >= 2023000000 ORDER BY reg_no", (p,))
    students = cursor.fetchall()
    print(f"Total regular students: {len(students)}")
    if not students:
        continue
        
    suffixes = [int(str(s[0])[5:]) for s in students]
    print(f"Suffix range: {min(suffixes)} to {max(suffixes)}")
    
    # Let's probe the first and last student in this profile
    for idx, (reg_no, name) in enumerate([students[0], students[-1]]):
        label = "First" if idx == 0 else "Last"
        print(f"  Probing {label} student Reg: {reg_no} ({name})...")
        data = {'pro_id': pro_id, 'sess_id': '24', 'exam_id': exam_id, 'gdata': '99', 'reg_no': str(reg_no)}
        html = cs.make_request(cs.AJAX_URL, data=data)
        if html:
            col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
            if col_m:
                college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip()
                print(f"  >>> COLLEGE: {college}")
            else:
                print("  >>> College not found in HTML!")
        else:
            print("  >>> Failed to fetch HTML")
