import sys
sys.path.insert(0, '.')
import cli_scraper as cs
import re

reg = "2023052952"
sess = "24"
exam = "1368"

print(f"Fetching result for Reg: {reg}, Sess: {sess}, Exam: {exam}")
data = {'pro_id': '13', 'sess_id': sess, 'exam_id': exam, 'gdata': '99', 'reg_no': reg}
html = cs.make_request(cs.AJAX_URL, data=data)

if html:
    print("SUCCESS!")
    # Let's extract the college name
    col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
    if col_m:
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip()
        print(f"COLLEGE: {college}")
    else:
        print("College not found in HTML!")
        
    name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
    if name_m:
        name = re.sub(r'<[^>]*>', '', name_m.group(1)).strip()
        print(f"NAME: {name}")
    else:
        print("Name not found in HTML!")
else:
    print("Failed to fetch HTML.")
