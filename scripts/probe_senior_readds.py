"""
probe_senior_readds.py
-----------------------
Safely probes registration ranges for Sessions 23 (Batch 10), 22 (Batch 09), 
and 21 (Batch 08) against Exam ID 1375 to locate re-admitted (re-add) and retake students.
Integrates these students into found_results_cse11_exam1375.json and result_finder.db.
"""

import sys
import os
import threading
import queue
import re
import json
import time
import random

sys.path.insert(0, '.')
import cli_scraper as cs
import database as db

# ── Modulo-10 Checksum Generator ───────────────────────────────────────────

def get_check_digit(year_str, suffix_str):
    total_sum = sum(int(d) for d in year_str + suffix_str)
    return (10 - (total_sum % 10)) % 10

def generate_registration(year, suffix):
    year_str = str(year)
    suffix_str = str(suffix).zfill(5)
    c = get_check_digit(year_str, suffix_str)
    return f"{year_str}{c}{suffix_str}"

# ── Dynamic Parser ──────────────────────────────────────────────────────────

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

# ── Main Probing Function ──────────────────────────────────────────────────

def main():
    print("=== STARTING CSE 11 EXAM 1375 SENIOR RE-ADD PROBE ===")
    
    # ── Establish Target Registrations ──
    targets = []
    
    # 1. Session 23 (Batch 10)
    # FEC Range: 54810 to 54890
    for suffix in range(54810, 54891):
        reg = generate_registration(2022, suffix)
        targets.append((reg, '23'))
    # MEC, Shyamoli, NITER Contiguous Range: 54940 to 55290
    for suffix in range(54940, 55291):
        reg = generate_registration(2022, suffix)
        targets.append((reg, '23'))
        
    # 2. Session 22 (Batch 09)
    # NITER Block: 430 to 520
    for reg_no in range(430, 521):
        targets.append((str(reg_no), '22'))
    # Shyamoli Block: 540 to 610
    for reg_no in range(540, 611):
        targets.append((str(reg_no), '22'))
    # MEC Block: 660 to 730
    for reg_no in range(660, 731):
        targets.append((str(reg_no), '22'))
    # FEC Block: 900 to 1050
    for reg_no in range(900, 1051):
        targets.append((str(reg_no), '22'))
    # High-range Block (other seniors): 2980 to 3090
    for reg_no in range(2980, 3091):
        targets.append((str(reg_no), '22'))
        
    # 3. Session 21 (Batch 08)
    # NITER Block: 430 to 520
    for reg_no in range(430, 521):
        targets.append((str(reg_no), '21'))
    # Shyamoli Block: 540 to 610
    for reg_no in range(540, 611):
        targets.append((str(reg_no), '21'))
    # MEC Block: 660 to 730
    for reg_no in range(660, 731):
        targets.append((str(reg_no), '21'))
    # FEC Block: 990 to 1040
    for reg_no in range(990, 1041):
        targets.append((str(reg_no), '21'))
    # High-range Block (other seniors): 2980 to 3090
    for reg_no in range(2980, 3091):
        targets.append((str(reg_no), '21'))

    # De-duplicate targets
    unique_targets = sorted(list(set(targets)))
    print(f"Generated {len(unique_targets)} unique candidate registrations to probe.")

    # Reference subject fingerprint from CSE 11
    ref_subjects = {'EEE-1103', 'CSE-1101', 'CHE-1114', 'CHE-1104', 'MATH-1105', 'CSE-1102', 'CSE-1111', 'SS-1106', 'EEE-1113'}
    print(f"Reference subject fingerprint: {ref_subjects}")

    # Set up thread worker
    results = []
    results_lock = threading.Lock()
    task_queue = queue.Queue()
    blocked_event = threading.Event()
    
    for item in unique_targets:
        task_queue.put(item)
        
    total_tasks = task_queue.qsize()
    completed = [0]

    # Warm up session cookies
    cs.make_request(cs.BASE_URL)
    
    def worker():
        while True:
            if blocked_event.is_set():
                time.sleep(10)
                blocked_event.clear()
            try:
                reg, sess_id = task_queue.get(timeout=2)
            except queue.Empty:
                break
                
            data = {
                'pro_id': '14',
                'sess_id': sess_id,
                'exam_id': '1375',
                'gdata': '99',
                'reg_no': reg
            }
            
            html = cs.make_request(cs.AJAX_URL, data=data)
            
            if html is None:
                task_queue.task_done()
                continue
                
            if "student" in html.lower() and "name" in html.lower():
                info = parse_student_html(html, reg, sess_id)
                if info and info['Name'] != 'Unknown' and info['Subjects']:
                    # Check subject overlap to verify it's indeed CSE 11 1st Year 1st Sem 2024 Exam
                    cand_subjects = {s['code'] for s in info['Subjects']}
                    overlap = cand_subjects & ref_subjects
                    
                    if len(overlap) >= 4:
                        with results_lock:
                            results.append(info)
                            print(f"FOUND SENIOR [{len(results)}] Reg {reg} (Session {sess_id}) | {info['Name'][:20]} | GPA: {info['GPA']} | {info['College'][:25]} | Subject Overlap: {len(overlap)}/{len(ref_subjects)}")
            
            with results_lock:
                completed[0] += 1
                if completed[0] % 100 == 0 or completed[0] == total_tasks:
                    print(f"Progress: {completed[0]}/{total_tasks} ({completed[0]*100//total_tasks}%) | Seniors Found: {len(results)}")
                    
            task_queue.task_done()
            time.sleep(random.uniform(0.30, 0.70))

    print(f"Launching crawl with 10 threads...")
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, daemon=True, name=f"Worker-{i}")
        t.start()
        threads.append(t)
        time.sleep(0.15)
        
    for t in threads:
        t.join()
        
    print(f"\nCrawling finished! Discovered {len(results)} senior re-add/retake student(s).")
    
    # ── Merge and Sync ──
    json_path = "found_results_cse11_exam1375.json"
    
    # Load existing regular batch students
    existing_students = []
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing_students = json.load(f)
            print(f"Loaded {len(existing_students)} regular students from {json_path}")
        except Exception as e:
            print(f"Error loading {json_path}: {e}")
            
    # Merge, keeping registrations unique
    all_students_dict = {}
    
    # Add regular batch first
    for s in existing_students:
        reg = s['Registration No']
        all_students_dict[reg] = s
        
    # Add discovered seniors
    new_seniors_added = 0
    for s in results:
        reg = s['Registration No']
        if reg not in all_students_dict:
            all_students_dict[reg] = s
            new_seniors_added += 1
            print(f"  + Merging Senior: {s['Name']} ({reg}) [Session {s['_sess_id']}] from {s['College']}")
        else:
            # Update subjects or overall results if already there
            all_students_dict[reg] = s
            
    merged_list = sorted(all_students_dict.values(), key=lambda r: (0, int(r['Registration No'])) if str(r['Registration No']).isdigit() else (1, str(r['Registration No'])))
    
    print(f"\nMerging complete! Total combined students in list: {len(merged_list)} (Added {new_seniors_added} new senior students).")
    
    # Write back to JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(merged_list, f, indent=4, ensure_ascii=False)
    print(f"Saved merged results (count {len(merged_list)}) to: {json_path}")
    
    # ── Database Sync ──
    print("\nSyncing all merged results to result_finder.db under profile 'cse 11'...")
    try:
        # Initialize profiles table for 'cse 11'
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
