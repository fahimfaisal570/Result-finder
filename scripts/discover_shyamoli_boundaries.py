import sys
sys.path.insert(0, '.')
import cli_scraper as cs
import re
import time

def get_check_digit(year_str, suffix_str):
    total_sum = sum(int(d) for d in year_str + suffix_str)
    return (10 - (total_sum % 10)) % 10

def generate_reg(year, suffix):
    year_str = str(year)
    suffix_str = str(suffix).zfill(5)
    c = get_check_digit(year_str, suffix_str)
    return f"{year_str}{c}{suffix_str}"

print("=== Mapping Shyamoli CSE 11 (Session 2023-24) Exact Suffixes ===")
# Scan 52810 to 52866 in steps of 2 to find any Shyamoli student
for suffix in range(52810, 52867, 2):
    reg = generate_reg(2023, suffix)
    data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
        name = re.sub(r'<[^>]*>', '', name_m.group(1)).strip() if name_m else "Unknown"
        print(f"  FOUND! Suffix: {suffix} | Reg: {reg} | College: {college} | Name: {name}")
    else:
        print(f"  Suffix {suffix} (Reg: {reg}) not found.")
    time.sleep(0.1)
