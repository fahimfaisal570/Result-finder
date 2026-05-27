import sys
sys.path.insert(0, '.')
import cli_scraper as cs
import re
import time
import concurrent.futures

def get_check_digit(year_str, suffix_str):
    total_sum = sum(int(d) for d in year_str + suffix_str)
    return (10 - (total_sum % 10)) % 10

def generate_reg(year, suffix):
    year_str = str(year)
    suffix_str = str(suffix).zfill(5)
    c = get_check_digit(year_str, suffix_str)
    return f"{year_str}{c}{suffix_str}"

def probe_suffix(suffix):
    reg = generate_reg(2023, suffix)
    data = {'pro_id': '14', 'sess_id': '24', 'exam_id': '1375', 'gdata': '99', 'reg_no': reg}
    html = cs.make_request(cs.AJAX_URL, data=data)
    if html and "Student's Name" in html:
        col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
        college = re.sub(r'<[^>]*>', '', col_m.group(1)).strip() if col_m else "Unknown"
        name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
        name = re.sub(r'<[^>]*>', '', name_m.group(1)).strip() if name_m else "Unknown"
        return suffix, reg, college, name
    return None

print("=== Probing Gap 52927 to 53166 (FEC to NITER) for CSE 11 (Session 24) ===")
# Probing with ThreadPoolExecutor for speed and robustness
found_results = []
suffixes_to_probe = list(range(52927, 53167))

# Initialize cookies
cs.make_request(cs.BASE_URL)

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(probe_suffix, sf): sf for sf in suffixes_to_probe}
    for count, future in enumerate(concurrent.futures.as_completed(futures)):
        res = future.result()
        if res:
            sf, reg, col, name = res
            print(f"  FOUND! Suffix: {sf} | Reg: {reg} | College: {col} | Name: {name}")
            found_results.append(res)
        if (count + 1) % 50 == 0:
            print(f"Progress: {count + 1}/{len(suffixes_to_probe)} probed.")

print(f"\nProbing finished! Found {len(found_results)} student(s) in the gap.")
for r in found_results:
    print(f"  Suffix: {r[0]} | Reg: {r[1]} | College: {r[2]} | Name: {r[3]}")
