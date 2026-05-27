import sqlite3
import sys
sys.path.insert(0, '.')
import cli_scraper as cs
import re

conn = sqlite3.connect("result_finder.db")

print("=== CSE 10 (Session 23) REGULAR STUDENTS ===")
cursor = conn.execute("SELECT reg_no, name FROM students WHERE profile_name = 'cse 10' AND reg_no >= 2022000000 ORDER BY reg_no")
students = cursor.fetchall()
print(f"Total students found: {len(students)}")

# Let's extract suffixes and group them
suffixes = []
for row in students:
    reg = str(row[0])
    suffix = int(reg[5:])
    suffixes.append((reg, suffix, row[1]))

suffixes.sort(key=lambda x: x[1])

# Group into contiguous blocks
blocks = []
current_block = []
for item in suffixes:
    if not current_block:
        current_block.append(item)
    else:
        if item[1] - current_block[-1][1] <= 10:  # within 10 numbers
            current_block.append(item)
        else:
            blocks.append(current_block)
            current_block = [item]
if current_block:
    blocks.append(current_block)

print(f"\nFound {len(blocks)} suffix blocks:")
for i, b in enumerate(blocks):
    print(f"\nBlock {i+1}:")
    print(f"  Count: {len(b)}")
    print(f"  Suffix Range: {b[0][1]} to {b[-1][1]}")
    print(f"  Reg Range: {b[0][0]} to {b[-1][0]}")
    
    # Probe the first student in the block to find their college!
    probe_reg = b[0][0]
    # We will fetch using program_id='14', exam_id='1047' (CSE 2nd Year 1st Sem 2023) or '1375' or similar.
    # Let's see if we can find their exam_id in the DB first.
    exam_cursor = conn.execute("SELECT exam_id, exam_name FROM exam_results WHERE profile_name = 'cse 10' AND reg_no = ?", (int(probe_reg),))
    exam_row = exam_cursor.fetchone()
    if exam_row:
        exam_id, exam_name = exam_row
        print(f"  Probing using Exam ID {exam_id} ({exam_name})...")
        data = {'pro_id': '14', 'sess_id': '23', 'exam_id': exam_id, 'gdata': '99', 'reg_no': probe_reg}
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
    else:
        print("  >>> No exam result in DB to probe!")
