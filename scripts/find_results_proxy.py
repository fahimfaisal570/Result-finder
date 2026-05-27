"""
find_results_proxy.py
---------------------
Full wide-scan: regs 1-5000, sessions 21 (main), 20 (senior-1), 19 (senior-2).

Fixes:
  - Correct name extraction using <th>Student's Name</th> pattern directly
  - College extracted before calling fetch_student_result to avoid re-request
  - 10 threads, 300-700ms delay per thread = safe, won't get banned
  - 60s backoff on BLOCKED/CAPTCHA, up to 3 retries per task on network error
"""
import sys, os, threading, queue, re, json, time, random, io

sys.path.insert(0, '.')
import cli_scraper as cs

# ── Config ────────────────────────────────────────────────────────────────────
PRO_ID   = '14'
EXAM_ID  = '1769'
SESSIONS = ['21', '20', '19']   # main, senior-1, senior-2
REG_START, REG_END = 1, 5000

NUM_THREADS = 10
DELAY_MIN   = 0.30
DELAY_MAX   = 0.70
BACKOFF_SEC = 60
MAX_REQUEUE = 3

# ── Shared state ──────────────────────────────────────────────────────────────
results       = []
results_lock  = threading.Lock()
task_queue    = queue.Queue()
blocked_event = threading.Event()
requeue_count = {}
requeue_lock  = threading.Lock()

for sess in SESSIONS:
    for reg in range(REG_START, REG_END + 1):
        task_queue.put((reg, sess))

TOTAL     = task_queue.qsize()
completed = [0]


def parse_student(html, reg, sess):
    """
    Parse student info directly from raw HTML, bypassing fetch_student_result's
    broken name regex. Uses <th>Student's Name</th> pattern directly.
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
        '_sess_id': sess,
    }

    # College Name — always first row
    col_m = re.search(r'<th>College\s*Name</th>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S)
    if col_m:
        info['College'] = re.sub(r'<[^>]*>', '', col_m.group(1)).strip()

    # Student Name — direct match on the th label, no lookahead trickery
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

    # Subjects
    subjects = []
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
        subjects.append({'code': code.strip().upper().replace(' ', '-'), 'name': subj_name, 'grade': grade_val, 'gp': gp_val})

    info['Subjects'] = subjects
    return info


def worker():
    while True:
        if blocked_event.is_set():
            print('[!] Block detected - sleeping %ds ...' % BACKOFF_SEC, flush=True)
            time.sleep(BACKOFF_SEC)
            blocked_event.clear()

        try:
            reg, sess = task_queue.get(timeout=2)
        except queue.Empty:
            break

        data = {'pro_id': PRO_ID, 'sess_id': sess, 'exam_id': EXAM_ID, 'gdata': '99', 'reg_no': str(reg)}
        html = cs.make_request(cs.AJAX_URL, data=data)
        key  = (reg, sess)

        if html is None:
            with requeue_lock:
                cnt = requeue_count.get(key, 0) + 1
                requeue_count[key] = cnt
            if cnt <= MAX_REQUEUE:
                task_queue.put(key)
            task_queue.task_done()
            time.sleep(random.uniform(1.0, 2.0))
            continue

        html_l = html.lower()
        if 'challenge' in html_l or 'captcha' in html_l or 'blocked' in html_l:
            blocked_event.set()
            task_queue.put(key)
            task_queue.task_done()
            continue

        if "student" in html_l and "name" in html_l:
            info = parse_student(html, reg, sess)
            if info and info['Name'] != 'Unknown':
                with results_lock:
                    results.append(info)
                    print('FOUND [%d] Reg %s | %-10s | SGPA %-4s | %s | %s' % (
                        len(results), info['Registration No'], info['Overall Result'],
                        info['GPA'], info['College'][:35], info['Name']
                    ), flush=True)

        with results_lock:
            completed[0] += 1
            if completed[0] % 200 == 0:
                pct = completed[0] * 100 // TOTAL
                print('Progress: %d/%d (%d%%) | Found: %d' % (completed[0], TOTAL, pct, len(results)), flush=True)

        task_queue.task_done()
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def main():
    print('Full rescan: regs %d-%d, sessions %s' % (REG_START, REG_END, SESSIONS), flush=True)
    print('Total tasks: %d | Threads: %d | Delay: %.1f-%.1fs' % (TOTAL, NUM_THREADS, DELAY_MIN, DELAY_MAX), flush=True)

    print('Warming up session cookie...', flush=True)
    warm = cs.make_request(cs.BASE_URL)
    if warm:
        print('Session ready.', flush=True)
    else:
        print('[!] Cannot reach portal. Check network.', flush=True)
        sys.exit(1)
    time.sleep(1.5)

    threads = []
    for i in range(NUM_THREADS):
        t = threading.Thread(target=worker, daemon=True, name='Worker-%d' % (i+1))
        t.start()
        threads.append(t)
        time.sleep(0.2)

    for t in threads:
        t.join()

    print('\nScan complete. Total found: %d' % len(results), flush=True)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'found_results.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print('Saved: %s' % out, flush=True)
    print('Run: python generate_pdf.py', flush=True)


if __name__ == '__main__':
    main()
