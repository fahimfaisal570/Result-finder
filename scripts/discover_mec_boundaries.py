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

print("=== Mapping MEC CSE 11 (Session 2023-24) Exact Suffixes ===")
# Scan 52700 to 52764 to find start of MEC
mec_start = None
for suffix in range(52700, 52766):
    reg = generate_reg(2023, suffix)
    data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
        name = re.sub(r'<[^>]*>', '', name_m.group(1)).strip() if name_m else "Unknown"
        if "Mymensingh" in college:
            mec_start = suffix
            print(f"MEC Start Suffix: {suffix} (Reg: {reg}) | Name: {name} | College: {college}")
            break
    time.sleep(0.1)

# Scan 52806 to 52820 to find end of MEC
mec_end = None
for suffix in range(52806, 52825):
    reg = generate_reg(2023, suffix)
    data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
        name = re.sub(r'<[^>]*>', '', name_m.group(1)).strip() if name_m else "Unknown"
        if "Mymensingh" in college:
            mec_end = suffix
            print(f"Found MEC suffix {suffix} in upper search (Reg: {reg}) | Name: {name}")
    else:
        # First non-existent student marks the end
        if mec_end is None:
            # We found the end previously or it wasn't found
            pass
    time.sleep(0.1)
