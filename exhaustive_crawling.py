"""
exhaustive_crawling.py
-----------------------
Systematically and exhaustively probes all potential registration number blocks 
across ALL relevant sessions (24, 23, 22, 21, 20, 19, 18) for B.Sc. in CSE (Program 14)
against Exam ID 1375 (CSE 11 1st Year 1st Sem Exam) to discover EVERY participating student.
Integrates newly found records into found_results_cse11_exam1375.json and result_finder.db.
"""

import sys
import os
import threading
import queue
import re
import json
import time
import random
import concurrent.futures
from collections import defaultdict


sys.path.insert(0, '.')
import cli_scraper as cs
import database as db

# ── Modulo-10 Checksum Generator for 10-digit Registrations ────────────────

def get_check_digit(year_str, suffix_str):
    total_sum = sum(int(d) for d in year_str + suffix_str)
    return (10 - (total_sum % 10)) % 10

def generate_registration(year, suffix):
    year_str = str(year)
    suffix_str = str(suffix).zfill(5)
    c = get_check_digit(year_str, suffix_str)
    return f"{year_str}{c}{suffix_str}"

# ── Robust Student HTML Parser ─────────────────────────────────────────────

def parse_student_html(html, reg, sess_id):
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#039;', "'")
    if "Student's Name" not in html and "Student&#039;s Name" not in html:
        return None

    info = {
        'Registration No': reg,
        'Name': 'Unknown',
        'Overall Result': '-',
        'GPA': '-',
        'CGPA': '-',
        'Pub Date': '-',
        'College': 'Unknown',
        '_sess_id': sess_id,
        'Subjects': []
    }

    # College Name
    col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
    if col_m:
        info['College'] = re.sub(r'<[^>]*>', '', col_m.group(1)).strip()

    # Student Name
    name_m = re.search(r"<th>Student'?s?\s*Name</th>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S)
    if name_m:
        info['Name'] = re.sub(r'<[^>]*>', '', name_m.group(1)).strip()

    # Publication date
    pub_m = re.search(r'Publication\s*Date.*?(\d{2}-\d{2}-\d{4})', html, re.I | re.S)
    if pub_m:
        info['Pub Date'] = pub_m.group(1)

    # GPA / CGPA
    gp_m = re.findall(r'(?:C\.?G\.?P\.?A\.?|G\.?P\.?A\.?)[^\d]*([\d.]+)', html, re.I)
    if gp_m:
        info['GPA']  = gp_m[0]
        info['CGPA'] = gp_m[1] if len(gp_m) > 1 else gp_m[0]

    # Overall Result
    res_m = re.search(r'<div[^>]*>\s*(Promoted|Passed|Failed|Withheld|Not Promoted)\b', html, re.I)
    if res_m:
        info['Overall Result'] = res_m.group(1)
    else:
        res_m2 = re.search(r'\b(Promoted|Passed|Failed|Withheld|Not Promoted)\b', html, re.I)
        if res_m2:
            info['Overall Result'] = res_m2.group(1)

    # Subject Grades
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S | re.I)
    for row in rows:
        cells = re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', row, re.S | re.I)
        cells = [re.sub(r'<[^>]*>', '', c).strip() for c in cells]
        if len(cells) < 3:
            continue
        code = None
        for c in cells:
            if re.match(r'^[A-Z]{2,6}[\-\s]*\d{3,4}\*?$', c, re.I):
                code = c
                break
        if not code:
            continue
        try:
            ci = cells.index(code)
            rest = cells[ci+1:]
        except:
            rest = cells
        gp_val, grade_val, subj_name = '0.00', '-', 'Unknown'
        for c in reversed(rest):
            if re.match(r'^[\d.]+$', c):
                try: gp_val = str(round(min(float(c), 4.0), 2))
                except: pass
                break
        for c in rest:
            if re.match(r'^[A-D][+\-]?$|^\bF\b$|^\bI\b$', c, re.I):
                grade_val = c
                break
        candidates = [c for i, c in enumerate(cells) if i != cells.index(code) and len(c) > 3 and not re.match(r'^[\d.\-]+$', c)]
        if candidates:
            subj_name = max(candidates, key=len)
        info['Subjects'].append({
            'code': code.strip().upper().replace(' ', '-'),
            'name': subj_name,
            'grade': grade_val,
            'gp': gp_val
        })

    return info

# ── Generate Targets Exhaustively ──────────────────────────────────────────

def get_exhaustive_targets():
    targets = []
    
    # 1. Session 24 registrations starting with 2023 (main batch regular range)
    reg_2023 = [generate_registration(2023, suffix) for suffix in range(52700, 53301)]
    
    # 2. Session 23 registrations starting with 2022 (Batch 10 regular range)
    reg_2022 = [generate_registration(2022, suffix) for suffix in range(54800, 55301)]
    
    # 3. Numeric registrations blocks across all colleges
    numeric_blocks = [
        (430, 750),    # Covers NITER, Shyamoli, MEC blocks
        (900, 1060),   # Covers FEC block
        (1740, 1820),  # Covers cse 05 and cse 06 blocks
        (2380, 2430),  # Shyamoli High block
        (2840, 2920),  # MEC High block
        (3000, 3100)   # FEC High block
    ]
    numeric_regs = []
    for start, end in numeric_blocks:
        for r in range(start, end + 1):
            numeric_regs.append(str(r))
            
    # --- Generate targets by combining registrations and active sessions ---
    
    # A. Probe everything under Session 24 (the main batch session)
    # Crucial for senior students readded with the main batch under Session 24!
    for r in reg_2023:
        targets.append((r, '24'))
    for r in reg_2022:
        targets.append((r, '24'))
    for r in numeric_regs:
        targets.append((r, '24'))
        
    # B. Probe everything under Session 23 (Batch 10)
    # For students readded or retaking Batch 11 exams under Session 23
    for r in reg_2022:
        targets.append((r, '23'))
    for r in numeric_regs:
        targets.append((r, '23'))
        
    # C. Probe numeric registrations under all senior Sessions 22, 21, 20, 19, 18, 17, 16
    for sess in ['22', '21', '20', '19', '18', '17', '16']:
        for r in numeric_regs:
            targets.append((r, sess))
            
    # De-duplicate and sort
    unique_targets = sorted(list(set(targets)))
    return unique_targets


# ── Main Exhaustive Crawler ────────────────────────────────────────────────

def main():
    print("=== STARTING EXHAUSTIVE AND WATER-TIGHT STUDENT SCAN FOR EXAM 1375 ===")
    
    targets = get_exhaustive_targets()
    total_targets = len(targets)
    print(f"Generated {total_targets} unique candidate registrations to probe across Sessions 18-24.")
    
    # CSE 1st Year 1st Sem Course Fingerprint
    ref_subjects = {'EEE-1103', 'CSE-1101', 'CHE-1114', 'CHE-1104', 'MATH-1105', 'CSE-1102', 'CSE-1111', 'SS-1106', 'EEE-1113'}
    print(f"Subject fingerprint for identification: {ref_subjects}")
    
    # Session cookies warm-up
    cs.make_request(cs.BASE_URL)
    
    found_students = []
    found_lock = threading.Lock()
    completed_count = [0]
    
    def probe_worker(reg, sess_id):
        time.sleep(random.uniform(0.05, 0.20))
        data = {
            'pro_id': '14',
            'sess_id': sess_id,
            'exam_id': '1375',
            'gdata': '99',
            'reg_no': reg
        }
        html = cs.make_request(cs.AJAX_URL, data=data)
        if html is None:
            return
            
        if "student" in html.lower() and "name" in html.lower():
            info = parse_student_html(html, reg, sess_id)
            if info and info['Name'] != 'Unknown' and info['Subjects']:
                # Identify as a participating student if there is ANY overlap with CSE 11 subjects (at least 1)
                cand_subjects = {s['code'] for s in info['Subjects']}
                overlap = cand_subjects & ref_subjects
                
                if len(overlap) >= 1:
                    with found_lock:
                        found_students.append(info)
                        print(f"  >>> FOUND STUDENT [{len(found_students)}] Reg: {reg} (Session {sess_id}) | Name: {info['Name'][:20]} | College: {info['College'][:25]} | GPA: {info['GPA']} | Overlap: {len(overlap)}")
                        
        with found_lock:
            completed_count[0] += 1
            if completed_count[0] % 250 == 0 or completed_count[0] == total_targets:
                print(f"Progress: {completed_count[0]}/{total_targets} ({completed_count[0]*100//total_targets}%) | Found: {len(found_students)}")

    # Launching execution with max_workers=20 for rapid and safe scanning
    print("\nLaunching concurrent workers...")
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(probe_worker, reg, sess_id) for reg, sess_id in targets]
        concurrent.futures.wait(futures)
        
    duration = time.time() - start_time
    print(f"\nExhaustive crawl completed in {duration:.1f} seconds!")
    print(f"Total participating students found: {len(found_students)}")
    
    # Group and analyze found students
    colleges = defaultdict(list)
    sessions = defaultdict(list)
    for s in found_students:
        colleges[s['College']].append(s)
        sessions[s['_sess_id']].append(s)
        
    print("\nScrape Summary by College:")
    for col, s_list in sorted(colleges.items()):
        print(f"  {col}: {len(s_list)}")
        
    print("\nScrape Summary by Session:")
    for sess, s_list in sorted(sessions.items()):
        print(f"  Session {sess}: {len(s_list)}")
        
    # ── Merge and Sync ──
    json_path = "found_results_cse11_exam1375.json"
    
    # Load existing results (if any)
    existing_students = []
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing_students = json.load(f)
            print(f"\nLoaded {len(existing_students)} existing records from {json_path}")
        except Exception as e:
            print(f"Error loading {json_path}: {e}")
            
    # Merge, keeping registrations unique and prioritizing newer/complete scrapings
    all_students_dict = {}
    
    for s in existing_students:
        reg = s['Registration No']
        all_students_dict[reg] = s
        
    new_additions = 0
    for s in found_students:
        reg = s['Registration No']
        if reg not in all_students_dict:
            all_students_dict[reg] = s
            new_additions += 1
            print(f"  + New Student Found & Added: {s['Name']} ({reg}) [Session {s['_sess_id']}] from {s['College']}")
        else:
            # Update to ensure latest parsed content
            all_students_dict[reg] = s
            
    # Sort the final merged list
    merged_list = sorted(
        all_students_dict.values(),
        key=lambda r: (0, int(r['Registration No'])) if str(r['Registration No']).isdigit() else (1, str(r['Registration No']))
    )
    
    print(f"\nMerged dataset size: {len(merged_list)} students (Added {new_additions} new student(s)).")
    
    # Write back to JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(merged_list, f, indent=4, ensure_ascii=False)
    print(f"Saved merged dataset to: {json_path}")
    
    # Sync to Database
    print("\nSyncing merged dataset to result_finder.db under profile 'cse 11'...")
    try:
        db.save_profile_and_results(
            profile_name='cse 11',
            pro_id='14',
            sess_id='24',
            results_list=merged_list,
            exam_id='1375',
            exam_name='B.Sc. in CSE Batch 11 1st Year 1st Semester Exam - 2025'
        )
        print("Database sync completed successfully!")
    except Exception as e:
        print(f"Error syncing to database: {e}")

if __name__ == '__main__':
    main()
