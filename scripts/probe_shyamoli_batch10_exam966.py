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

# Probe the gap between MEC and NITER for Shyamoli CSE 10 under Exam 966
print("Probing gap 55061-55124 under Exam 966...")
for suffix in range(55065, 55125, 5):
    reg = generate_reg(2022, suffix)
    print(f"Probing Suffix {suffix} (Reg: {reg})...")
    data = {'pro_id': '14', 'sess_id': '23', 'exam_id': '966', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        name = re.sub(r'<[^>]*>', '', name_m.group(1)).strip() if name_m else "Unknown"
        print(f"  >>> FOUND! Suffix: {suffix} | Reg: {reg} | College: {college} | Name: {name}")
    else:
        print("  Not found.")
    time.sleep(0.2)
