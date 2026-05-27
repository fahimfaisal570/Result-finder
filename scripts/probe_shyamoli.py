import sys
sys.path.insert(0, '.')
import cli_scraper as cs
import re

def get_check_digit(year_str, suffix_str):
    total_sum = sum(int(d) for d in year_str + suffix_str)
    return (10 - (total_sum % 10)) % 10

def generate_reg(year, suffix):
    year_str = str(year)
    suffix_str = str(suffix).zfill(5)
    c = get_check_digit(year_str, suffix_str)
    return f"{year_str}{c}{suffix_str}"

reg = generate_reg(2023, 52830)
print(f"Probing Suffix 52830 (Reg: {reg}) for Shyamoli Engineering College...")
data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
html = cs.make_request(cs.AJAX_URL, data=data)

if html and "Student's Name" in html:
    col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
    name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
    college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
    name = re.sub(r'<[^>]*>', '', name_m.group(1)).strip() if name_m else "Unknown"
    print(f"SUCCESS! College: {college} | Name: {name}")
else:
    print("Not found or failed.")
