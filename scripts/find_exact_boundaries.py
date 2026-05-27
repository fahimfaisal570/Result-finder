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

# 1. Probe MEC CSE 11 range (52650 to 52866) in steps of 5 first to find start/end
print("Probing MEC range (52650 to 52866)...")
for suffix in range(52650, 52867, 5):
    reg = generate_reg(2023, suffix)
    data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        print(f"  FOUND MEC: Suffix: {suffix} | Reg: {reg} | College: {college}")
    time.sleep(0.1)

# 2. Probe the space between FEC and NITER (52927 to 53199) in steps of 5 to locate Shyamoli
print("\nProbing intermediate range (52927 to 53199)...")
for suffix in range(52927, 53200, 5):
    reg = generate_reg(2023, suffix)
    data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        print(f"  FOUND: Suffix: {suffix} | Reg: {reg} | College: {college}")
    time.sleep(0.1)

# 3. Probe NITER and above (53200 to 53450) in steps of 5
print("\nProbing NITER & above range (53200 to 53450)...")
for suffix in range(53200, 53451, 5):
    reg = generate_reg(2023, suffix)
    data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        print(f"  FOUND NITER: Suffix: {suffix} | Reg: {reg} | College: {college}")
    time.sleep(0.1)
