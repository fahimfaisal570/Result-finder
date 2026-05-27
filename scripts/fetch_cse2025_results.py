"""
fetch_cse2025_results.py
-------------------------
A dedicated, premium-quality script to scrape CSE 11/12 1st Year 1st Semester 2025
results for MEC, FEC, and NITER using the 10-digit Modulo-10 checksum registration algorithm.

Usage:
  python fetch_cse2025_results.py --exam_id <EXAM_ID> --batch 11

Ensure 'cli_scraper.py' is present in the same directory.
"""
import sys
import os
import threading
import queue
import re
import json
import time
import random
import argparse
import subprocess

sys.path.insert(0, '.')
import cli_scraper as cs

# ── Checksum & Registration Generator ─────────────────────────────────────────

def calculate_check_digit(year_str, suffix_str):
    """
    Computes the 5th digit (checksum) for the 10-digit registration number.
    Ensures that the sum of all 10 digits is a multiple of 10.
    """
    total_sum = sum(int(d) for d in year_str + suffix_str)
    return (10 - (total_sum % 10)) % 10

def generate_registration(year, suffix):
    """
    Generates a full 10-digit registration number.
    Format: YYYY C SSSSS
    """
    year_str = str(year)
    suffix_str = str(suffix).zfill(5)
    c = calculate_check_digit(year_str, suffix_str)
    return f"{year_str}{c}{suffix_str}"

# ── Dynamic Suffix Range Map ──────────────────────────────────────────────────

COLLEGE_RANGES = {
    # Mymensingh Engineering College (MEC)
    'MEC': (52756, 52815),
    # Faridpur Engineering College (FEC)
    'FEC': (52867, 52926),
    # National Institute of Textile Engineering & Research (NITER)
    'NITER': (53147, 53260)
}

def build_target_registrations(batch_year):
    """
    Generates target 10-digit registration numbers for MEC, FEC, and NITER.
    """
    targets = []
    for college_name, (start, end) in COLLEGE_RANGES.items():
        print(f"Generating registrations for {college_name} (Suffixes {start} to {end})...")
        for suffix in range(start, end + 1):
            reg = generate_registration(batch_year, suffix)
            targets.append((reg, college_name))
    return targets

# ── Robust Scraper Parser ─────────────────────────────────────────────────────

def parse_student_html(html, reg, sess_id):
    """
    Parses name, college, GPA, CGPA, and subjects from the student result HTML.
    """
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

# ── Scraper Worker Core ───────────────────────────────────────────────────────

def run_scraper(exam_id, sess_id, target_regs):
    """
    Safely crawls student results using 10 threads, randomized delays, and blocked backoffs.
    """
    results = []
    results_lock = threading.Lock()
    task_queue = queue.Queue()
    blocked_event = threading.Event()
    requeue_count = {}
    requeue_lock = threading.Lock()
    
    for reg, col in target_regs:
        task_queue.put((reg, col))
        
    total_tasks = task_queue.qsize()
    completed = [0]
    
    print("\nWarming up session cookie...", end='', flush=True)
    warm = cs.make_request(cs.BASE_URL)
    if warm:
        print(" Connected successfully.")
    else:
        print("\n[!] Error: Unable to reach portal. Please verify internet connection.")
        return []
    
    time.sleep(1.0)
    
    def worker():
        while True:
            if blocked_event.is_set():
                time.sleep(60) # Slepp on CAPTCHA / blockage
                blocked_event.clear()
                
            try:
                reg, col = task_queue.get(timeout=2)
            except queue.Empty:
                break
                
            data = {
                'pro_id': '14', # CSE
                'sess_id': sess_id,
                'exam_id': exam_id,
                'gdata': '99',
                'reg_no': str(reg)
            }
            
            html = cs.make_request(cs.AJAX_URL, data=data)
            key = reg
            
            if html is None:
                with requeue_lock:
                    cnt = requeue_count.get(key, 0) + 1
                    requeue_count[key] = cnt
                if cnt <= 3:
                    task_queue.put((reg, col))
                task_queue.task_done()
                time.sleep(1.5)
                continue
                
            html_l = html.lower()
            if 'challenge' in html_l or 'captcha' in html_l or 'blocked' in html_l:
                blocked_event.set()
                task_queue.put((reg, col))
                task_queue.task_done()
                continue
                
            if "student" in html_l and "name" in html_l:
                info = parse_student_html(html, reg, sess_id)
                if info and info['Name'] != 'Unknown':
                    with results_lock:
                        results.append(info)
                        print(f"FOUND [{len(results)}] Reg {reg} | {info['Name'][:20]} | GPA: {info['GPA']} | {info['College'][:25]}")
            
            with results_lock:
                completed[0] += 1
                if completed[0] % 20 == 0 or completed[0] == total_tasks:
                    print(f"Progress: {completed[0]}/{total_tasks} ({completed[0]*100//total_tasks}%) | Found: {len(results)}")
                    
            task_queue.task_done()
            time.sleep(random.uniform(0.30, 0.70)) # Safe randomized interval
            
    print(f"Starting crawl with 10 threads...")
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, daemon=True, name=f"Worker-{i}")
        t.start()
        threads.append(t)
        time.sleep(0.15)
        
    for t in threads:
        t.join()
        
    print(f"\nCrawling finished! Total records successfully scraped: {len(results)}")
    return results

# ── Print-Ready PDF/HTML Generator ──────────────────────────────────────────

def generate_report(results, exam_title, filename_prefix="cse_batch11"):
    # Sort by Registration No
    results.sort(key=lambda r: (0, int(r['Registration No'])) if str(r['Registration No']).isdigit() else (1, str(r['Registration No'])))

    # Split into regular batch vs re-adds (senior session)
    # The default batch session is '24' for batch 11 (Session 2023-24)
    main_sess = '24'
    main_list  = [r for r in results if str(r.get('_sess_id', main_sess)) == main_sess]
    readd_list = [r for r in results if str(r.get('_sess_id', main_sess)) != main_sess]

    # Scholarship / GPA ranking (only include valid numbers)
    valid_gpa = sorted(
        [(float(r['GPA']), r) for r in results if r.get('GPA', '-') not in ('-', '', None) and str(r['GPA']).replace('.', '').isdigit()],
        key=lambda x: x[0], reverse=True
    )
    top_half = (len(valid_gpa) + 1) // 2

    # CGPA ranking
    valid_cgpa = sorted(
        [(float(r['CGPA']), r) for r in results if r.get('CGPA', '-') not in ('-', '', None) and str(r['CGPA']).replace('.', '').isdigit()],
        key=lambda x: x[0], reverse=True
    )

    import datetime
    timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap');

    * { box-sizing: border-box; margin: 0; padding: 0; }

    @page {
        size: 230mm 8500mm; /* Continuous scroll: massive height for 168 students */
        margin: 0;
    }

    body {
        font-family: 'Outfit', Arial, sans-serif;
        background: #fff;
        color: #000;
        padding: 40px;
        font-size: 14px;
    }

    #cli-report-root .container { max-width: 960px; margin: 0 auto; }

    #cli-report-root .report-block {
        background: #fff;
        padding: 20px;
        margin-bottom: 30px;
        border: 1px solid #ccc;
    }

    #cli-report-root .title-section {
        text-align: center;
        margin-bottom: 18px;
        border-bottom: 2px solid #000;
        padding-bottom: 12px;
    }

    #cli-report-root .title-section h1 {
        font-size: 18px;
        font-weight: 700;
        color: #000;
        margin-bottom: 4px;
    }

    #cli-report-root .title-section h2 {
        font-size: 14px;
        font-weight: 600;
        color: #000;
        margin-bottom: 4px;
        border: none;
        padding: 0;
    }

    #cli-report-root .summary-text {
        font-size: 13px;
        font-weight: bold;
        color: #333;
    }

    #cli-report-root h2 {
        font-size: 14px;
        font-weight: 700;
        margin: 14px 0 8px 0;
        color: #000;
        border-left: 4px solid #000;
        padding-left: 8px;
    }

    #cli-report-root .table-container {
        overflow-x: visible;
        margin-top: 10px;
    }

    #cli-report-root table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        margin-bottom: 15px;
        table-layout: auto;
    }

    #cli-report-root th {
        background: #f4f4f4;
        color: #000;
        font-weight: bold;
        text-align: center;
        text-transform: uppercase;
        font-size: 12px;
    }

    #cli-report-root th, #cli-report-root td {
        padding: 8px 10px;
        text-align: left;
        border: 1px solid #000;
    }

    #cli-report-root td.center { text-align: center; }

    #cli-report-root .col-sl  { width: 45px;  text-align: center; }
    #cli-report-root .col-reg { width: 95px;  text-align: center; }
    #cli-report-root .col-res { width: 85px;  text-align: center; }
    #cli-report-root .col-gpa,
    #cli-report-root .col-cgpa { width: 60px; text-align: center; }
    #cli-report-root .col-college { width: 190px; }

    #cli-report-root .data-bold { font-weight: bold; }
    #cli-report-root .award-text { font-weight: bold; font-style: italic; }

    @media print {
        body { padding: 40px; }
        #cli-report-root .report-block { border: 1px solid #999; }
    }
    </style>
    """

    def render_table(data_list, title_text, is_readd=False):
        if not data_list:
            return ""
        html_tbl = f"<h2>{title_text} ({len(data_list)})</h2>"
        html_tbl += """<div class='table-container'><table><thead><tr>
            <th class='col-sl'>Sl</th>
            <th class='col-reg'>Reg No</th>
            <th>Name</th>
            <th class='col-college'>College / Institute</th>
            <th class='col-res'>Result</th>
            <th class='col-gpa'>SGPA</th>
            <th class='col-cgpa'>CGPA</th>
        </tr></thead><tbody>"""

        for sl, res in enumerate(data_list, 1):
            reg_val = str(res['Registration No'])
            sess_tag = ""
            if is_readd:
                sess_tag = f" <small style='font-size:0.8em;'>[{res.get('_sess_id', '?')}]</small>"
            college = res.get('College', '-')
            html_tbl += (
                f"<tr>"
                f"<td class='col-sl center'>{sl}</td>"
                f"<td class='col-reg data-bold'>{reg_val}{sess_tag}</td>"
                f"<td>{res['Name']}</td>"
                f"<td class='col-college'>{college}</td>"
                f"<td class='col-res center'>{res['Overall Result']}</td>"
                f"<td class='col-gpa data-bold center'>{res['GPA']}</td>"
                f"<td class='col-cgpa data-bold center'>{res['CGPA']}</td>"
                f"</tr>"
            )

        html_tbl += "</tbody></table></div>"
        return html_tbl

    parts = [f"<div id='cli-report-root'>{css}<div class='container'>"]

    # Block 1: Results
    parts.append("<div class='report-block'>")
    parts.append(f"""
        <div class='title-section'>
            <h1>All Affiliated Colleges &amp; Institutes</h1>
            <h2>{exam_title}</h2>
            <span class='summary-text'>
                All-College Result Report | Total Students Found: {len(results)}
                | Generated: {timestamp_str}
            </span>
        </div>
    """)
    parts.append(render_table(main_list,  f"Registration-Wise Result (Regular Batch - Session 2023-24)"))
    parts.append(render_table(readd_list, "Registration-Wise Result (Re-adds / Senior Batches)", is_readd=True))
    parts.append("</div>")  # end block 1

    # Block 2: Scholarship eligibility (ranked by SGPA)
    if valid_gpa:
        parts.append("<div class='report-block'><h2>Scholarship Eligibility List (Ranked by SGPA)</h2>")
        parts.append("""<div class='table-container'><table><thead><tr>
            <th class='col-sl'>Rank</th>
            <th class='col-reg'>Reg No</th>
            <th>Name</th>
            <th class='col-college'>College / Institute</th>
            <th class='col-gpa'>SGPA</th>
            <th class='col-award'>Status</th>
        </tr></thead><tbody>""")
        for sl, (gpa_val, res) in enumerate(valid_gpa, 1):
            eligible = "<span class='award-text'>Eligible</span>" if sl <= top_half else ""
            parts.append(
                f"<tr>"
                f"<td class='col-sl center'>{sl}</td>"
                f"<td class='col-reg data-bold center'>{res['Registration No']}</td>"
                f"<td>{res['Name']}</td>"
                f"<td class='col-college'>{res.get('College', '-')}</td>"
                f"<td class='col-gpa data-bold center'>{res['GPA']}</td>"
                f"<td class='center'>{eligible}</td>"
                f"</tr>"
            )
        parts.append("</tbody></table></div></div>")

    # Block 3: CGPA ranking
    if valid_cgpa:
        parts.append("<div class='report-block'><h2>Overall Batch CGPA Ranking</h2>")
        parts.append("""<div class='table-container'><table><thead><tr>
            <th class='col-sl'>Rank</th>
            <th class='col-reg'>Reg No</th>
            <th>Name</th>
            <th class='col-college'>College / Institute</th>
            <th class='col-cgpa'>CGPA</th>
        </tr></thead><tbody>""")
        for sl, (cgpa_val, res) in enumerate(valid_cgpa, 1):
            parts.append(
                f"<tr>"
                f"<td class='col-sl center'>{sl}</td>"
                f"<td class='col-reg data-bold center'>{res['Registration No']}</td>"
                f"<td>{res['Name']}</td>"
                f"<td class='col-college'>{res.get('College', '-')}</td>"
                f"<td class='col-cgpa data-bold center'>{res['CGPA']}</td>"
                f"</tr>"
            )
        parts.append("</tbody></table></div></div>")

    parts.append("</div></div>")
    html_content = "".join(parts)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{exam_title}</title>
</head>
<body>
{html_content}
</body>
</html>"""

    html_file = f"{filename_prefix}_report.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(full_html)
    print(f"HTML Report generated: {html_file}")
    
    # Try to render PDF using Edge headless
    pdf_file = f"{filename_prefix}_report.pdf"
    edge = None
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.exists(p):
            edge = p
            break
            
    if edge:
        print("Rendering PDF via MS Edge headless...")
        html_abs_path = os.path.abspath(html_file)
        pdf_abs_path = os.path.abspath(pdf_file)
        html_url = "file:///" + html_abs_path.replace("\\", "/")
        cmd = [
            edge,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-software-rasterizer",
            "--run-all-compositor-stages-before-draw",
            f"--print-to-pdf={pdf_abs_path}",
            "--no-pdf-header-footer",
            html_url,
        ]
        subprocess.run(cmd, check=False)
        if os.path.exists(pdf_file) and os.path.getsize(pdf_file) > 1000:
            print(f"Premium print-ready PDF generated successfully: {pdf_file}")
            return
            
    print("[!] MS Edge not found. Open the HTML file in any browser and print manually to PDF.")

# ── Main Entry ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape B.Sc. CSE 1st Year 1st Sem 2025 results across 4 colleges.")
    parser.add_argument('--exam_id', type=str, required=True, help="Exam ID from the DUCMC portal (obtain using fetch_cse_exams.py)")
    parser.add_argument('--batch', type=int, choices=[11, 12], default=11, help="Admission Batch (11 for Session 2023-24 [Prefix 2023], 12 for Session 2024-25 [Prefix 2024])")
    args = parser.parse_args()
    
    # Map batches to sessions: Session 24 is Batch 11, Session 25 is Batch 12
    sess_id = '24' if args.batch == 11 else '25'
    batch_year = 2023 if args.batch == 11 else 2024
    
    print(f"=== CSE BATCH {args.batch} RESULT CRAWLER ===")
    print(f"Targeting: CSE Batch {args.batch} (Admission Year {batch_year}, Session ID {sess_id})")
    print(f"Targeting Exam ID: {args.exam_id}")
    print("---------------------------------------")
    
    target_regs = build_target_registrations(batch_year)
    results = run_scraper(args.exam_id, sess_id, target_regs)
    
    if not results:
        print("No student records found. Scrape aborted.")
        return
        
    # Save raw json output
    json_path = f"found_results_cse{args.batch}_exam{args.exam_id}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print(f"Raw data saved to: {json_path}")
    
    exam_title = f"B.Sc. in CSE Batch {args.batch} 1st Year 1st Semester Exam - 2025"
    generate_report(results, exam_title, f"cse_batch{args.batch}_results")

if __name__ == '__main__':
    main()
