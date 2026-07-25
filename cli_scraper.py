#!/usr/bin/env python3
"""
Dynamic DUCMC Scraper - Android (Pydroid 3) Edition
---------------------------------------------------
Instructions for Pydroid 3:
1. Copy this entire script.
2. Open Pydroid 3 on your Android phone.
3. Create a new file, paste this code, and save it (e.g., as ducmc.py).
4. Press the "Play" button to run.
5. The HTML report will automatically open in your default browser.
"""

import os
import sys
import time
import re
import collections
import random
import urllib.parse as urllib_parse
import queue
input_func = input
import json
import database as db
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx, add_report_ctx
except ImportError:
    get_script_run_ctx = add_report_ctx = lambda *args, **kwargs: None

import threading

# --- Scraper Configuration ---
BASE_URL = "https://ducmc.du.ac.bd/"
AJAX_URL = "https://ducmc.du.ac.bd/ajax/get_program_by_exam.php"
PROGRAM_AJAX_URL = "https://ducmc.du.ac.bd/ajax/get_program_by_course.php"
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
]

# Shared Caches (for Web Dashboard integration)
SESSIONS_CACHE = {}
PROGRAMS_CACHE = {}

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Origin': 'https://ducmc.du.ac.bd',
    'Referer': 'https://ducmc.du.ac.bd/result.php',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'X-Requested-With': 'XMLHttpRequest'
}

# Session Globals
SESSION_UA = random.choice(USER_AGENTS)

# Robust path resolution for Android persistence
ORIGINAL_DIR = os.getcwd()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) or ORIGINAL_DIR


import requests
from requests.adapters import HTTPAdapter

session = requests.Session()
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=100, max_retries=0)
session.mount("https://", adapter)
session.mount("http://", adapter)

import concurrent.futures

def warm_connection_pool(num_connections=6):
    """
    Concurrently warms the requests session connection pool to minimize cold-start SSL/TLS handshake latency.
    Runs (num_connections - 1) HEAD requests and 1 GET request in parallel.
    """
    req_headers = HEADERS.copy()
    req_headers['User-Agent'] = SESSION_UA

    def _warm_single(method):
        try:
            if method == "GET":
                response = session.get(BASE_URL, headers=req_headers, timeout=15)
                return response.status_code
            else:
                response = session.request("HEAD", BASE_URL, headers=req_headers, timeout=15)
                return response.status_code
        except Exception:
            return None

    # Prepare methods: 1 GET (to fetch and establish cookies) and remaining as HEAD
    methods = ["GET"] + ["HEAD"] * max(0, num_connections - 1)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_connections) as executor:
        futures = [executor.submit(_warm_single, m) for m in methods]
        concurrent.futures.wait(futures)

global_backoff_until = 0

# Compiled regular expressions for robust, zero-dependency HTML parsing
PAT_PUB_DATE_1 = re.compile(r"Publication\s*Date.*?(\d{2}-\d{2}-\d{4})", re.I | re.S)
PAT_PUB_DATE_2 = re.compile(r"Date\s*of\s*Publication.*?(\d{2}-\d{2}-\d{4})", re.I | re.S)
PAT_STUDENT_NAME = re.compile(r"(?:Student\'?s?\s*)?\bName\b(?!.*College).*?<td[^>]*>\s*(.*?)\s*</td>", re.I | re.S)
PAT_STUDENT_NAME_FB = re.compile(r"(?:Student\'?s?\s+)?Name\s*[:\-]?\s*<[^>]+>\s*([^<]+)", re.I)
PAT_GPA_CGPA = re.compile(r'(?:C\.?G\.?P\.?A\.?|G\.?P\.?A\.?|S\.?G\.?P\.?A\.?|Y\.?G\.?P\.?A\.?)[^\d]*([\d\.]+)', re.I)
PAT_OVERALL_RESULT = re.compile(r'(?:Overall\s+)?Result[^\w]*<td[^>]*>(.*?)</td>', re.I | re.S)
PAT_STATUS_MATCH = re.compile(r'\b(Promoted|Passed|Failed|Withheld|Not Promoted)\b', re.I)
PAT_TABLE_ROWS = re.compile(r'<tr[^>]*>(.*?)</tr>', re.I | re.S)
PAT_TABLE_CELLS = re.compile(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', re.I | re.S)
PAT_TAGS = re.compile(r'<[^>]*>')
PAT_SUBJECT_CODE = re.compile(r'^[A-Z]{2,6}[\-\s]*\d{3,4}[\*]*$', re.I)
PAT_SUBJECT_GP = re.compile(r'^[\d\.]+$')
PAT_SUBJECT_GRADE = re.compile(r'^[A-D][\+\-]?$|^\bF\b$|^\bI\b$|^\bW\b$', re.I)

_stealth_lock = None

def get_stealth_lock():
    global _stealth_lock
    if _stealth_lock is None:
        _stealth_lock = threading.Lock()
    return _stealth_lock


class BatchManager:
    @property
    def profiles(self):
        """Returns dict keyed by profile name, fetched from SQLite."""
        return db.get_profiles()
        
    def save_new_batch(self, name, regs_data, sess_id=None, pro_id=None, latest_exam_id=None):
        # Prepare a dummy results list for save_profile_and_results
        results_list = []
        for item in regs_data:
            if isinstance(item, (list, tuple)):
                results_list.append({
                    "Registration No": int(item[0]),
                    "_sess_id": str(item[1]),
                    "Name": item[2] if len(item) > 2 else "Unknown"
                })
            else:
                results_list.append({
                    "Registration No": int(item),
                    "_sess_id": str(sess_id or "AUTO"),
                    "Name": "Unknown"
                })
        db.save_profile_and_results(name, pro_id or "0", sess_id or "AUTO", results_list, latest_exam_id or "0", "Initial Scan")
    def update_batch_info(self, name, sess_id=None, pro_id=None, latest_exam_id=None):
        db.update_profile_metadata(name, pro_id=pro_id, sess_id=sess_id)
            
    def add_to_batch(self, name, regs_data):
        for item in regs_data:
            if isinstance(item, (list, tuple)):
                db.upsert_student(name, int(item[0]), str(item[2] if len(item) > 2 else "Unknown"), str(item[1]))
            else:
                db.upsert_student(name, int(item), "Unknown", "AUTO")
            
    def remove_from_batch(self, name, rs_rem):
        for r in rs_rem:
            reg = int(r)
            # Query all session variants for this reg_no
            with db.get_connection() as conn:
                variants = conn.execute(
                    "SELECT sess_id, name FROM students WHERE profile_name=? AND reg_no=?",
                    (name, reg)
                ).fetchall()
            if not variants:
                print(f"  Student {reg} not found in '{name}'.")
                continue
            if len(variants) == 1:
                db.remove_student_from_profile(name, reg, variants[0][0])
            else:
                print(f"\n  Multiple entries found for reg {reg}:")
                for i, (sid, sname) in enumerate(variants, 1):
                    print(f"    [{i}] {sname} (session: {sid})")
                print("    [A] Remove ALL")
                choice = input_func(f"  Which one to remove? (1-{len(variants)} or A): ").strip()
                if choice.upper() == 'A':
                    for sid, _ in variants:
                        db.remove_student_from_profile(name, reg, sid)
                else:
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(variants):
                            db.remove_student_from_profile(name, reg, variants[idx][0])
                        else:
                            print("  Invalid choice. Skipped.")
                    except ValueError:
                        print("  Invalid choice. Skipped.")
            
    def delete_batch(self, name):
        db.delete_profile(name)

    def save_profiles(self):
        """No-op for SQLite backend as writes are immediate."""
        return True

    def save_provisional_to_json(self, name, pro_id, sess_id, regs):
        """Save a provisional batch to saved_profiles.json (main branch storage)."""
        profiles_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_profiles.json")
        profiles_dict = {}
        if os.path.exists(profiles_path):
            try:
                with open(profiles_path, "r") as f:
                    profiles_dict = json.load(f)
            except Exception:
                pass
        
        profiles_dict[name] = {
            "pro_id": pro_id,
            "sess_id": sess_id,
            "regs": [[r, sess_id, "Unknown"] for r in regs],
            "is_provisional": True
        }
        
        try:
            with open(profiles_path, "w") as f:
                json.dump(profiles_dict, f, indent=2)
        except Exception as e:
            print(f"Error saving to saved_profiles.json: {e}")

batch_manager = BatchManager()



def make_request(url, data=None, headers=None, retries=4):
    """Makes HTTP requests with full session awareness using requests.Session."""
    req_headers = HEADERS.copy()
    req_headers['User-Agent'] = SESSION_UA
    
    if headers: 
        req_headers.update(headers)
        
    for attempt in range(retries):
        try:
            if data:
                response = session.post(url, data=data, headers=req_headers, timeout=15)
            else:
                response = session.get(url, headers=req_headers, timeout=15)
                
            if response.status_code in (200, 301, 302):
                return response.content.decode('utf-8', 'ignore')
        except Exception:
            pass
            
        if attempt < retries - 1:
            sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
            time.sleep(sleep_time)
            
    return None

def get_relevant_exams(sess_id, sessions, all_exams):
    """
    Consolidated cohort exam year filtering logic.
    Given a session ID, matches the start year and filters exams
    to only probe exams from the student's cohort year onward (with a 1-year buffer).
    """
    import re
    start_search_year = 0
    if sess_id and sess_id != "AUTO":
        sess_name = sessions.get(sess_id, "")
        y_match = re.search(r"20(\d{2})", sess_name)
        if y_match:
            start_search_year = int("20" + y_match.group(1))

    EXAM_YEAR_PATTERN = re.compile(r'\b(20\d{2})\b')
    filtered_exam_ids = []
    for eid, ename in all_exams.items():
        if start_search_year:
            matches = EXAM_YEAR_PATTERN.findall(ename)
            ey = int(matches[-1]) if matches else 0
            if ey and ey < (start_search_year - 1):
                continue
        filtered_exam_ids.append(eid)
    return filtered_exam_ids

def format_session(sess_id):
    """Transforms session notation into the standard '21-22' format."""
    # Handle already formatted strings or session names
    if "-" in str(sess_id) and len(str(sess_id)) <= 5: return sess_id
    
    # Try to extract a 4-digit year (e.g. 2021)
    s_str = str(sess_id)
    year_match = re.search(r"(20\d{2})", s_str)
    if year_match:
        y = int(year_match.group(1))
        return "{}-{}".format(y-2000, y-1999)
    
    # Handle 2-digit numeric input
    if s_str.isdigit() and len(s_str) == 2:
        y = int(s_str)
        return "{}-{}".format(y, y+1)
        
    return sess_id

def extract_options_from_html(html):
    pattern = r'<option[^>]+value\s*=\s*["\']?([^"\'>\s]*)["\']?[^>]*>(.*?)</option>'
    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
    results = []
    for val, text in matches:
        clean_text = re.sub(r'<[^>]*>', '', text).strip()
        if val: results.append((val, clean_text))
    return results

def fetch_programs_and_sessions():
    """Fetches sessions and programs, ensuring a valid session cookie exists."""
    cached = db.get_meta_cache("portal_meta", ttl_seconds=86400)
    if cached and cached.get("programs") and cached.get("sessions"):
        PROGRAMS_CACHE.update(cached["programs"])
        SESSIONS_CACHE.update(cached["sessions"])
        return collections.OrderedDict(cached["programs"]), collections.OrderedDict(cached["sessions"])

    # Ensure a session handshake (visit BASE_URL) if cookies are missing when reaching out to portal.
    if not session.cookies:
        make_request(BASE_URL)

    html = make_request("https://ducmc.du.ac.bd/result.php")
    if not html: 
        print("[!] Failed to connect to {} - Check your internet.".format("result.php"))
        return collections.OrderedDict(), collections.OrderedDict()
    
    programs = collections.OrderedDict()
    sessions = collections.OrderedDict()
    
    select_blocks = re.findall(r'<select.*?</select>', html, re.DOTALL | re.IGNORECASE)
    for block in select_blocks:
        options = extract_options_from_html(block)
        if not options: continue
        
        block_lower = block.lower()
        first_opt_text = options[0][1].lower() if options else ""
        
        if 'id="sess_id"' in block_lower or 'session' in first_opt_text or 'session_id' in block_lower:
            for val, text in options: sessions[val] = text
        elif 'id="pro_id"' in block_lower or 'course name' in first_opt_text or 'course_name' in block_lower:
             for val, text in options: 
                 if val != "0": programs[val] = text
                
    # Apply Sorting, Formatting, and Discipline Filtering
    if programs:
        whitelist = ["computer science", "civil engineering", "electrical and electronic"]
        filtered = {k: v for k, v in programs.items() 
                   if "b.sc." in v.lower() and any(w in v.lower() for w in whitelist)}
        # Sort programs alphabetically by name
        sorted_pgs = sorted(filtered.items(), key=lambda x: x[1])
        programs = collections.OrderedDict(sorted_pgs)
        
    if sessions:
        # Format session names and sort by year descending
        formatted_sess = []
        for sid, sname in sessions.items():
            fname = format_session(sname)
            # Filter: only keep sessions starting from 2016-17 onwards
            # Matches "2016", "2017", or "16", "17" in the formatted string
            year_match = re.search(r"(\d{2,4})", fname)
            if year_match:
                year_val = int(year_match.group(1))
                if year_val >= 2016 or (year_val >= 16 and year_val < 100):
                    formatted_sess.append((sid, fname))
        
        # Sort by the formatted name descending (e.g. 21-22 > 20-21)
        formatted_sess.sort(key=lambda x: x[1], reverse=True)
        sessions = collections.OrderedDict(formatted_sess)
                    
    if not programs: 
        print("[!] Warning: Zero programs identified. Chained menu crawl failed.")
    else:
        db.set_meta_cache("portal_meta", {"programs": dict(programs), "sessions": dict(sessions)})
    
    PROGRAMS_CACHE.update(programs)
    SESSIONS_CACHE.update(sessions)
    return programs, sessions

def fetch_exams(pro_id):
    cache_key = "exams_{}".format(pro_id)
    cached = db.get_meta_cache(cache_key, ttl_seconds=3600)  # Cache hourly
    if cached:
        return collections.OrderedDict(cached)
    url = "{0}?program_id={1}&pedata=99".format(AJAX_URL, pro_id)
    html = make_request(url)
    if not html: return collections.OrderedDict()
    options = extract_options_from_html(html)
    res = collections.OrderedDict(options)
    db.set_meta_cache(cache_key, dict(res))
    return res

def run_batch_scan_engine(tasks, pro_id, exam_id="0", all_sessions=None, progress_callback=None, target_college="all", num_threads=5):
    """
    Unified CLI-Native scanning engine. 
    Tasks can be (reg, sess) or (reg, sess, exam).
    """
    # Ensure session handshake and connection pool are warmed up
    if not session.cookies:
        warm_connection_pool(num_connections=6)
    if not all_sessions:
        fetch_programs_and_sessions()
        
    # Immediate Startup Feedback: Update the UI right now so user knows we are active
    if progress_callback:
        try: progress_callback(0, len(tasks), "Engine firing up... Probing portal.")
        except: pass
    
    results_lock = threading.Lock()
    print_lock = threading.Lock()
    completed_tasks = [0]
    all_results = []
    
    task_queue = queue.Queue()
    for t in tasks: task_queue.put(t)
    
    progress_queue = queue.Queue()
    def wrapped_callback(current, total, status_text=None):
        progress_queue.put((current, total, status_text))

    # Launch worker threads
    worker_count = min(num_threads, len(tasks))
    t_args = (task_queue, pro_id, exam_id, all_results, results_lock, print_lock, len(tasks), completed_tasks, target_college, all_sessions, wrapped_callback)
    threads = []
    for _ in range(worker_count):
        time.sleep(random.uniform(0.01, 0.04))  # Stagger handshakes to prevent rate-limiting/timeouts
        t = threading.Thread(target=worker_thread, args=t_args)
        t.daemon = True; t.start(); threads.append(t)
        
    # Main thread processes the queue while workers run
    while any(t.is_alive() for t in threads) or not progress_queue.empty():
        try:
            p_data = progress_queue.get(timeout=0.1)
            if progress_callback:
                try: progress_callback(*p_data)
                except: pass
            progress_queue.task_done()
        except queue.Empty:
            continue

    for t in threads: t.join()
    return all_results

def fetch_student_result(reg_no, pro_id, sess_id, exam_id, target_college="all"):
    data = {'pro_id': str(pro_id), 'sess_id': str(sess_id), 'exam_id': str(exam_id), 'gdata': '99', 'reg_no': str(reg_no)}
    html = make_request(AJAX_URL, data=data)
    if html is None: return "NETWORK_ERROR", False
    
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#039;', "'")
    
    if "Student's Name" not in html:
        if "no record found" in html.lower() or "not found" in html.lower() or "no data found" in html.lower():
            return "NOT_FOUND", False
        if "challenge" in html.lower() or "captcha" in html.lower() or "blocked" in html.lower():
            return "BLOCKED", False
        return "PARSING_ERROR (No Table Found)", False
    
    is_student_found = True
    if target_college != "all":
        norm_html = re.sub(r'\s+', ' ', html.lower())
        if target_college not in norm_html:
            return None, is_student_found
    info = {'Registration No': reg_no, 'Name': 'Unknown', 'Overall Result': '-', 'GPA': '-', 'CGPA': '-', 'Pub Date': '-'}
    
    # Resilient Publication Date Extraction
    pub_match = PAT_PUB_DATE_1.search(html) or PAT_PUB_DATE_2.search(html)
    if pub_match:
        info['Pub Date'] = pub_match.group(1)
    
    # Resilient Name Matching
    name_match = PAT_STUDENT_NAME.search(html)
    if name_match:
        info['Name'] = PAT_TAGS.sub('', name_match.group(1)).strip()
    else:
        name_fb = PAT_STUDENT_NAME_FB.search(html)
        if name_fb:
            info['Name'] = PAT_TAGS.sub('', name_fb.group(1)).strip()
        else:
            return "PARSING_ERROR (Name Not Found)", False
        
    # Flexible GPA/CGPA Extraction
    gp_m = PAT_GPA_CGPA.findall(html)
    if gp_m:
        if len(gp_m) == 1:
            info['GPA'] = gp_m[0]
        else:
            info['GPA'] = gp_m[0]
            info['CGPA'] = gp_m[1]
    
    # Overall Result
    res_explicit = PAT_OVERALL_RESULT.search(html)
    if res_explicit:
        info['Overall Result'] = PAT_TAGS.sub('', res_explicit.group(1)).strip()
    else:
        status_match = PAT_STATUS_MATCH.search(html)
        if status_match:
            info['Overall Result'] = status_match.group(1).strip()
            
    # Robust Subject Extraction Logic
    subjects = []
    rows = PAT_TABLE_ROWS.findall(html)
    
    for row_content in rows:
        cells = PAT_TABLE_CELLS.findall(row_content)
        cells = [PAT_TAGS.sub('', c).strip() for c in cells]
        
        if len(cells) < 3:
            continue
            
        code = None
        for c in cells:
            if PAT_SUBJECT_CODE.match(c):
                code = c
                break
        
        if not code:
            continue
            
        gp_val = "0.00"
        grade_val = "-"
        
        try:
            code_idx = cells.index(code)
            search_area = cells[code_idx+1:]
        except:
            search_area = cells
            
        for c in reversed(search_area):
            if PAT_SUBJECT_GP.match(c) or c == '-' or c.lower() in ['f', 'w', 'wh']:
                try:
                    gp_val = str(round(min(float(c), 4.0), 2))
                except (ValueError, TypeError):
                    gp_val = "0.00"
                break
        
        for c in search_area:
            if PAT_SUBJECT_GRADE.match(c):
                grade_val = c
                break
                
        subj_name = "Unknown"
        if len(cells) >= 3:
            try:
                code_idx = cells.index(code)
                candidates = [c for i, c in enumerate(cells) if i != code_idx and len(c) > 3 and not re.match(r'^[\d\.\-]+$', c)]
                if candidates:
                    subj_name = max(candidates, key=len)
            except:
                pass

        subjects.append({
            'code': code.strip().upper().replace(' ', '-'),
            'name': subj_name.strip(),
            'grade': grade_val.strip(),
            'gp': gp_val
        })
    info['Subjects'] = subjects
    
    info['_sess_id'] = sess_id
    return info, is_student_found

def generate_html_report(results, report_title, pro_id=None, sess_id=None):
    """Builds a responsive HTML report optimized for Mobile."""
    
    # Sort results by Registration No
    def get_reg_sort_key(res):
        try: return (0, int(res['Registration No']))
        except Exception: return (1, str(res['Registration No']))
    results.sort(key=get_reg_sort_key)
    
    # Ranking logic
    valid_gpa_results = []
    for res in results:
        try:
            gpa = float(res['GPA'])
            valid_gpa_results.append((gpa, res))
        except (ValueError, TypeError): pass
    valid_gpa_results.sort(key=lambda x: x[0], reverse=True)
    top_half_count = (len(valid_gpa_results) + 1) // 2

    valid_cgpa_results = []
    for res in results:
        try:
            cgpa = float(res['CGPA'])
            valid_cgpa_results.append((cgpa, res))
        except (ValueError, TypeError): pass
    valid_cgpa_results.sort(key=lambda x: x[0], reverse=True)
    css = """
    <style>
        body { 
            font-family: 'Times New Roman', Times, serif; 
            background-color: #fff; color: #000; line-height: 1.5; margin: 0; padding: 20px 10px;
        }
        #cli-report-root .container { max-width: 900px; margin: 0 auto; }
        #cli-report-root .report-block { 
            background: #fff; padding: 25px; border-radius: 0; margin-bottom: 40px;
            border: 1px solid #000;
            display: block;
            box-sizing: border-box;
            page-break-inside: avoid;
        }
        #cli-report-root .title-section { text-align: center; margin-bottom: 25px; border-bottom: 2px solid #000; padding-bottom: 15px; }
        #cli-report-root h1 { color: #000; font-size: 26px; margin: 0 0 5px 0; text-transform: uppercase; letter-spacing: 1px; }
        #cli-report-root h2 { 
            color: #000; font-size: 20px; margin: 20px 0 10px 0; font-weight: bold; 
            border-left: 5px solid #000; padding-left: 12px;
            page-break-after: avoid;
        }
        #cli-report-root .summary-text { font-size: 15px; font-weight: bold; color: #333; }
        #cli-report-root .table-container { overflow-x: visible; margin-top: 15px; page-break-inside: avoid; }
        #cli-report-root table { width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 20px; table-layout: auto; }
        #cli-report-root tr { page-break-inside: avoid; }
        #cli-report-root th { background: #f4f4f4; color: #000; font-weight: bold; text-align: center; text-transform: uppercase; font-size: 13px; }
        #cli-report-root th, #cli-report-root td { padding: 8px 10px; text-align: left; border: 1px solid #000; }
        #cli-report-root td.center { text-align: center; }
        #cli-report-root .col-sl { width: 45px; text-align: center; }
        #cli-report-root .col-reg { width: 90px; text-align: center; }
        #cli-report-root .col-res { width: 90px; text-align: center; }
        #cli-report-root .col-gpa, #cli-report-root .col-cgpa { width: 60px; text-align: center; }
        #cli-report-root .data-bold { font-weight: bold; }
        #cli-report-root .award-text { font-weight: bold; font-style: italic; }
    </style>
    """

    import datetime
    bd_time = datetime.datetime.utcnow() + datetime.timedelta(hours=6)
    timestamp_str = bd_time.strftime("%Y-%m-%d %H:%M:%S")

    html = ["<div id='cli-report-root'>", css, "<div class='container'>"]
    
    # --- Data Categorization (Main vs Re-adds) ---
    main_list = []
    readd_list = []
    for r in results:
        s_id_final = r.get('_sess_id', sess_id)
        if sess_id and str(s_id_final) != str(sess_id):
            readd_list.append(r)
        else:
            main_list.append(r)

    def render_results_table(data_list, title_text, is_readd=False):
        if not data_list: return ""
        sec_html = f"<h2>{title_text} ({len(data_list)})</h2>"
        sec_html += "<div class='table-container'><table><thead><tr><th class='col-sl'>Sl</th><th class='col-reg'>Reg No</th><th>Name</th><th class='col-res'>Result</th><th class='col-gpa'>SGPA</th><th class='col-cgpa'>CGPA</th></tr></thead><tbody>"
        
        for sl, res in enumerate(data_list, 1):
            reg_val = str(res['Registration No'])
            s_id_final = res.get('_sess_id', sess_id)
            name_display = res['Name']
            
            # Show session tag for re-adds
            reg_display = reg_val
            if is_readd:
                 reg_display = f"{reg_val} <small style='font-size:0.8em;'>[{s_id_final}]</small>"

            if pro_id and sess_id:
                # Removed <a> tag to eliminate underlines for PDF professional look
                name_display = res['Name']
                
            sec_html += "<tr><td class='col-sl center'>{0}</td><td class='col-reg data-bold'>{1}</td><td>{2}</td><td class='col-res center'>{3}</td><td class='col-gpa data-bold'>{4}</td><td class='col-cgpa data-bold'>{5}</td></tr>".format(
                sl, reg_display, name_display, res['Overall Result'], res['GPA'], res['CGPA']
            )
        sec_html += "</tbody></table></div>"
        return sec_html

    # Block 1: Results Summary (Categorized)
    html.append("<div class='report-block'><div class='title-section'><h1>Faridpur Engineering College</h1>")
    html.append(f"<h2>{report_title}</h2>")
    html.append(f"<span class='summary-text'>Official Batch Report &nbsp;|&nbsp; Generated: {timestamp_str}</span></div>")
    
    # 1. Main Batch Table (Registration Wise SGPA/CGPA)
    html.append(render_results_table(main_list, "Registration-Wise Result (Regular Batch)"))
    
    # 2. Re-adds Table
    html.append(render_results_table(readd_list, "Registration-Wise Result (Re-adds & Seniors)", is_readd=True))
    
    html.append("</div>") # End block 1
    
    # Block 2: Scholarship Eligibility (Ranked by SGPA)
    if valid_gpa_results:
        html.append("<div class='report-block'><h2>Scholarship Eligibility List (Ranked by SGPA)</h2>")
        html.append("<div class='table-container'><table><thead><tr><th class='col-sl'>Rank</th><th class='col-reg'>Reg No</th><th>Name</th><th class='col-gpa'>SGPA</th><th class='col-award'>Status</th></tr></thead><tbody>")
        for sl, item in enumerate(valid_gpa_results, 1):
            res = item[1]
            scholarship = "<span class='award-text'>Eligible</span>" if sl <= top_half_count else ""
            html.append("<tr><td class='col-sl center'>{0}</td><td class='col-reg data-bold center'>{1}</td><td>{2}</td><td class='col-gpa data-bold'>{3}</td><td class='col-award center'>{4}</td></tr>".format(
                sl, res['Registration No'], res['Name'], res['GPA'], scholarship
            ))
        html.append("</tbody></table></div></div>")
    
    # Block 3: CGPA Ranking List
    if valid_cgpa_results:
        html.append("<div class='report-block'><h2>Overall Batch CGPA Ranking</h2>")
        html.append("<div class='table-container'><table><thead><tr><th class='col-sl'>Rank</th><th class='col-reg'>Reg No</th><th>Name</th><th class='col-cgpa'>CGPA</th></tr></thead><tbody>")
        for sl, item in enumerate(valid_cgpa_results, 1):
            res = item[1]
            html.append("<tr><td class='col-sl center'>{0}</td><td class='col-reg data-bold center'>{1}</td><td>{2}</td><td class='col-cgpa data-bold'>{3}</td></tr>".format(
                sl, res['Registration No'], res['Name'], res['CGPA']
            ))
        html.append("</tbody></table></div></div>")
    
    html.append("</div></div>")
    return "".join(html)

def filter_dict_by_search(d, search_str):
    search_str = search_str.lower()
    return collections.OrderedDict((k, v) for k, v in d.items() if search_str in v.lower())

def prompt_selection(items_dict, prompt_text, default_idx=0):
    print("\n[ {0} ]".format(prompt_text))
    
    keys = list(items_dict.keys())
    if len(keys) == 1:
        print("Auto-selected: {0}".format(items_dict[keys[0]]))
        return keys[0], items_dict[keys[0]]
        
    filtered_items = items_dict
    if len(items_dict) > 20:
        search = input_func("Enter a search term (or press Enter to list all, 'b' for Back): ").strip()
        if search.lower() == 'b': return 'b', 'b'
        if search: filtered_items = filter_dict_by_search(items_dict, search)
    
    # Ensure items are sorted alphabetically by their display text
    sorted_items = sorted(filtered_items.items(), key=lambda x: x[1])
    keys = [item[0] for item in sorted_items]
    
    default_display = default_idx + 1 if default_idx < len(keys) else 1
    
    for i, key in enumerate(keys, 1): 
        ind = " [*]" if i == default_display else ""
        print("[{0}]{1} {2}".format(i, ind, dict(sorted_items)[key]))
        
    while True:
        try:
            choice = input_func("Select (1-{0}) (Enter for {1}): ".format(len(keys), default_display)).strip().lower()
            if choice == 'b': return 'b', 'b'
            
            if not choice:
                idx = default_display - 1
            else:
                idx = int(choice) - 1
                
            if 0 <= idx < len(keys): return keys[idx], filtered_items[keys[idx]]
        except: pass
        print("Invalid.")

def prompt_preloaded_program(items_dict):
    # Ground Truth IDs based on Live Site Audit
    c_id = "14" if "14" in items_dict else None
    e_id = "13" if "13" in items_dict else None
    cv_id = "12" if "12" in items_dict else None
        
    print("\n[ Select Discipline ]")
    print("[1] B.Sc. in Computer Science (CSE)" + ("" if c_id else " (N/A)"))
    print("[2] B.Sc. in Electrical and Electronic (EEE)" + ("" if e_id else " (N/A)"))
    print("[3] B.Sc. in Civil Engineering (Civil)" + ("" if cv_id else " (N/A)"))
    
    while True:
        c = input_func("Select (1-3) or 'b': ").strip().lower()
        if c == 'b': return 'b', 'b'
        if c == '1' and c_id: return c_id, items_dict[c_id]
        if c == '2' and e_id: return e_id, items_dict[e_id]
        if c == '3' and cv_id: return cv_id, items_dict[cv_id]
        print("Invalid.")

def prompt_custom_session(sessions, prompt_text):
    print("\n[ {0} ]".format(prompt_text))
    while True:
        c = input_func("Session (last 2 digits of HSC year) [e.g. 21] or 'l' to list all: ").strip().lower()
        if c == 'b': return 'b', 'b'
        if c == 'l': return prompt_selection(sessions, "All Sessions")
        
        if c.isdigit() and len(c) == 2:
            t = "20" + c
            for k, v in sessions.items():
                if t in v:
                    print("Auto-Matched: {}".format(v))
                    return k, v
        print("No match for '{}'. Try 'l' to list.".format(c))

def parse_range(range_str):
    if not range_str.strip(): return []
    result = []
    parts = [p.strip() for p in range_str.split(',') if p.strip()]
    for part in parts:
        try:
            bounds = part.split('-')
            if len(bounds) == 1: result.append(int(bounds[0].strip()))
            elif len(bounds) == 2: result.extend(list(range(int(bounds[0].strip()), int(bounds[1].strip()) + 1)))
        except ValueError:
            print("Ignoring invalid part: '{}'".format(part))
    return result

def parse_exam_info(name):
    name_lower = name.lower()
    legacy_map = {"part-i": 1, "part-ii": 2, "part-iii": 3, "part-iv": 4, "part i": 1, "part ii": 2, "part iii": 3, "part iv": 4}
    y = None
    for k, v in legacy_map.items():
        if k in name_lower: y = v; break
    if not y:
        y_match = re.search(r"(\d+)(?:st|nd|rd|th)?\s+Year|Year\s*[-\s]*(\d+)", name, re.I)
        y = int(y_match.group(1) or y_match.group(2)) if y_match else None
    s_match = re.search(r"(\d+)(?:st|nd|rd|th)?\s+Sem|Sem\s*[-\s]*(\d+)", name, re.I)
    sem = int(s_match.group(1) or s_match.group(2)) if s_match else 0
    
    # Normalize absolute semesters (1-8) used by older batches (e.g. 6th Sem -> Year 3, Sem 2)
    if sem > 2:
        if not y: y = (sem + 1) // 2
        sem = 1 if sem % 2 != 0 else 2
        
    ey_match = re.search(r"(?:Examination|Exam)[-\s]*(\d{4})|(?:\b|[^0-9])(20\d{2})(?:\b|[^0-9])", name, re.I)
    ey = int(ey_match.group(1) or ey_match.group(2)) if ey_match else None
    if "professional" in name_lower and not sem: sem = 1
    return y, sem, ey

def classify_exams(exams_dict, batch_session=None, probe_regs=None, pro_id=None, profile_name=None):
    """
    Precision Exam Classification System.
    Groups exams into exactly 8 'Main' semester slots and handles retakes/legacy formats.
    """
    mains_slots = {} # slot_idx -> list of [id, name, y, sem, ey, score]
    retakes = collections.OrderedDict()
    if not exams_dict: return collections.OrderedDict(), retakes

    # --- DB Cache ---
    import hashlib
    dict_sig = hashlib.md5(json.dumps(sorted(list(exams_dict.keys()))).encode()).hexdigest()
    if probe_regs and pro_id:
        cache_key = f"classify_probe_{profile_name or ''}_{pro_id}_{batch_session}_{dict_sig}"
    else:
        cache_key = f"classify_fast_{batch_session}_{dict_sig}"
    cached = db.get_meta_cache(cache_key, ttl_seconds=3600)
    if cached and "mains" in cached and "retakes" in cached:
        return collections.OrderedDict(cached["mains"]), collections.OrderedDict(cached["retakes"])
    
    # Identify batch start year
    batch_start_year = None
    if batch_session:
        s_match = re.search(r"(\d{4})", str(batch_session))
        if s_match: batch_start_year = int(s_match.group(1))

    # Extended Exclusion List
    exclusions = ["retake", "improvement", "clearance", "junior", "special", "backlog", "short", "carry"]
    
    for k, v in exams_dict.items():
        v_l = v.lower()
        if any(x in v_l for x in exclusions):
            retakes[k] = v; continue
            
        curr_y, curr_sem, curr_ey = parse_exam_info(v)
        
        # Look for explicit session year in parentheses like (2018-2019)
        name_sess_match = re.search(r"\((\d{4})[-\s]*\d{4}\)", v)
        name_sess_year = int(name_sess_match.group(1)) if name_sess_match else None
        
        # Determine if it's a 'Main' exam candidate
        is_candidate = False
        if not batch_start_year:
            is_candidate = True # Allow all if no session pinning
        elif name_sess_year is not None:
            # IF session is explicit, it MUST match exactly
            if name_sess_year == batch_start_year:
                is_candidate = True
            else:
                is_candidate = False # Hard-exclude mismatch
        elif curr_y and curr_ey:
            calc_inc = curr_ey - curr_y
            # Adaptive Year Tolerance fallback (only for exams without session tags)
            if batch_start_year < 2019:
                if calc_inc in [batch_start_year, batch_start_year + 1, batch_start_year - 1]:
                    is_candidate = True
            else:
                if calc_inc == batch_start_year:
                    is_candidate = True
        
        if is_candidate and curr_y:
            # Enforce 8-Exam Constraint (4 years * 2 semesters)
            # Default to sem 1 if missing for mapping
            s_idx = max(0, curr_sem - 1) if curr_sem else 0
            slot_idx = (curr_y - 1) * 2 + s_idx
            
            if 0 <= slot_idx < 8:
                # Scoring for de-duplication
                score = 0
                if batch_session and str(batch_session) in v: score += 10 # Session Tag Match
                
                # Boost if calendar offset matches explicit batch start year
                if batch_start_year and curr_y and curr_ey:
                    if (curr_ey - curr_y) == batch_start_year:
                        score += 20
                        
                v_slug = re.sub(r'\s+', ' ', v_l)
                if "new curriculum" in v_slug: score += 5
                if "old syllabus" in v_slug or "old curriculum" in v_slug: score -= 5
                
                if slot_idx not in mains_slots: mains_slots[slot_idx] = []
                mains_slots[slot_idx].append({'id': k, 'name': v, 'y': curr_y, 'sem': curr_sem, 'ey': curr_ey, 'score': score})
            else:
                retakes[k] = v
        else:
            retakes[k] = v

    # Final De-duplication & Probe Verification (Pick best passing candidate per slot)
    mains_final_list = []
    
    probe_sess_id = "AUTO"
    if probe_regs and pro_id:
        for ks, vs in SESSIONS_CACHE.items():
            if str(vs) == str(batch_session):
                probe_sess_id = ks
                break

    for slot_idx in sorted(mains_slots.keys()):
        candidates = mains_slots[slot_idx]
        # Sort by score desc, then by Exam ID desc (most recent)
        candidates.sort(key=lambda x: (x['score'], int(x['id'])), reverse=True)
        
        best = None
        for cand in candidates:
            if probe_regs and pro_id:
                is_valid = False
                
                # 1. Local DB Fast-Path: if saved results exist for this profile & exam, no network probe needed!
                if profile_name and db.has_exam_results_for_profile(profile_name, cand['id']):
                    is_valid = True
                else:
                    # 2. Parallel Network Probe (Fast multi-threaded verification)
                    import concurrent.futures
                    def _probe_single(pr):
                        try:
                            res, is_found = fetch_student_result(pr, pro_id, probe_sess_id, cand['id'])
                            return (is_found and res is not None and res not in ("NOT_FOUND", "NETWORK_ERROR", "BLOCKED"))
                        except Exception:
                            return False

                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(probe_regs), 5)) as executor:
                        futures = [executor.submit(_probe_single, pr) for pr in probe_regs]
                        for f in concurrent.futures.as_completed(futures):
                            if f.result():
                                is_valid = True
                                break

                if is_valid:
                    best = cand
                    break
                else:
                    retakes[cand['id']] = cand['name']
            else:
                best = cand
                break
        
        if best:
            mains_final_list.append((best['id'], best['name'], best['y'], best['sem'], best['ey']))
            # Add other candidates for this slot to retakes
            for cand in candidates:
                if cand['id'] != best['id'] and cand['id'] not in retakes:
                    retakes[cand['id']] = cand['name']

    # Final result sorting (Newest exams first for display)
    mains_final_list.sort(key=lambda x: (x[2], x[3], x[4]), reverse=True)
    mains = collections.OrderedDict()
    for i in mains_final_list: mains[i[0]] = i[1]
    
    if cache_key:
        db.set_meta_cache(cache_key, {"mains": dict(mains), "retakes": dict(retakes)})

    return mains, retakes
def handle_exam_selection(exams_dict, batch_session=None, probe_regs=None, pro_id=None):
    if not exams_dict: return ('b', None, False)
    mains, others = classify_exams(exams_dict, batch_session, probe_regs, pro_id)
    print("\n[ Select Examination ]")
    m_keys = list(mains.keys())
    if not m_keys:
        if str(batch_session).lower() != "any":
            print("ℹ️ No 'Main' exams detected for session '{}'.".format(batch_session))
    else:
        for i, k in enumerate(m_keys, 1): print("[{0}] {1}".format(i, mains[k]))
    
    nx = len(m_keys) + 1
    print("[{0}] ... List All / Retake Exams".format(nx))
    print("[{0}] ... Custom Search".format(nx + 1))
    print("[b] Back")
    
    while True:
        c = input_func("Choice: ").strip().lower()
        if c == 'b': return ('b', None, None)
        try:
            val = int(c)
            if 1 <= val <= len(m_keys): return m_keys[val-1], mains[m_keys[val-1]], False
            if val == nx:
                res = prompt_selection(others, "Other Exams")
                if res[0] != 'b': return res[0], res[1], False
                return handle_exam_selection(exams_dict, batch_session)
            if val == nx+1:
                w = input_func("Search: ").strip().lower()
                f = collections.OrderedDict([(k,v) for k,v in exams_dict.items() if w in v.lower()])
                res = prompt_selection(f, "Results")
                if res[0] != 'b': return res[0], res[1], False
                return handle_exam_selection(exams_dict, batch_session)
        except: pass
        print("Invalid.")

def worker_thread(task_queue, pro_id, exam_id_default, all_results, results_lock, print_lock, total_tasks, completed_tasks, target_college, all_sessions=None, progress_callback=None):
    while True:
        try: item = task_queue.get_nowait()
        except queue.Empty: break
        
        # Mandatory Human-like initial delay (Jitter) - Synced with CLI for performance
        time.sleep(random.uniform(0.02, 0.07))  # Jitter L3: was (0.04, 0.15)
        
        # Flex-tasks: (reg, sess) or (reg, sess, exam)
        if len(item) == 3:
            reg_no, sess_id, exam_id = item
        else:
            reg_no, sess_id = item
            exam_id = exam_id_default
        
        sessions_to_try = [sess_id]
        if sess_id == "AUTO" and all_sessions:
            sessions_to_try = list(all_sessions.keys())
            
        student_found_in_any_session = False
        
        for tsid in sessions_to_try:
            # Secondary jitter for session discovery - Synced with CLI for performance
            time.sleep(random.uniform(0.01, 0.02))  # Jitter L3: was (0.02, 0.05)
            
            if progress_callback:
                try: 
                    # Report granular status so user knows it's NOT stuck
                    progress_callback(completed_tasks[0], total_tasks, "Exam {0}: Checking Session {1}...".format(str(exam_id)[:10], tsid))
                except: pass
            retries = 0
            while True:
                time.sleep(random.uniform(0.01, 0.02))  # Jitter L3: was (0.02, 0.05)
                res, is_any = fetch_student_result(reg_no, pro_id, tsid, exam_id, target_college)
                if res == "NETWORK_ERROR":
                    retries += 1
                    if retries >= 3:
                        res = None; break
                    # Faster retry for dashboard responsiveness (2-5s instead of 10-15s)
                    time.sleep(random.uniform(2.0, 5.0))
                    continue
                
                # Robust Discovery Logic: Match CLI baseline (GPA or Subjects)
                if res and isinstance(res, dict) and (res.get('GPA', res.get('SGPA', '-')) != '-' or res.get('Subjects')):
                    student_found_in_any_session = True
                    break
                res = None; break
            if student_found_in_any_session: break
        
        with results_lock:
            completed_tasks[0] += 1
            current = completed_tasks[0]
            if res: 
                res['_exam_id'] = str(exam_id)
                res['_sess_id'] = str(tsid) # Store the session where student was found
                all_results.append(res)
            if progress_callback:
                try: progress_callback(current, total_tasks, "Finished Exam {0}".format(str(exam_id)[:10]))
                except: pass
                
        with print_lock:
            if res:
                print("[Checked: {0} / {1}] Reg {2} -> OK: {3}... | {4}".format(current, total_tasks, reg_no, res['Name'][:15], res['GPA']))
            else:
                print("[Checked: {0} / {1}] Reg {2} -> SKIP (Not found/Filtered)".format(current, total_tasks, reg_no))
            sys.stdout.flush()

def manage_profiles(programs, sessions):
    while True:
        print("\n--- Managed Saved Batch Profiles ---")
        profiles = batch_manager.profiles
        
        profile_names = sorted(list(profiles.keys()))
        for i, name in enumerate(profile_names):
            prof = profiles[name]
            print("[{0}] {1} ({2} students)".format(i+1, name, len(prof.get("regs", []))))
            
        if not profiles:
            print("(No profiles saved yet)")
            
        print("[i] Import Profiles from File")
        print("[b] Back")
        
        choice = input_func("Select Choice: ").strip().lower()
        if choice == 'b': return
        
        if choice == 'i':
            # Global Import Logic (moved from sub-menu)
            print("\n--- Import Profiles ---")
            downloads_dir = "/storage/emulated/0/Download"
            search_dirs = [SCRIPT_DIR]
            if os.path.exists(downloads_dir): search_dirs.append(downloads_dir)
            
            files = []
            for d in search_dirs:
                if not os.path.exists(d): continue
                for f in os.listdir(d):
                    if f.startswith("ducmc_export_") and f.endswith(".json"):
                        files.append(os.path.join(d, f))
                        
            if not files:
                print("No 'ducmc_export_*.json' files found in Download or Script directory.")
                continue
            else:
                for i, fpath in enumerate(files, 1):
                    print("[{}] {}".format(i, os.path.basename(fpath)))
                f_choice = input_func("Select file to import: ").strip()
                try:
                    f_idx = int(f_choice) - 1
                    if 0 <= f_idx < len(files):
                        with open(files[f_idx], 'r', encoding='utf-8') as f:
                            imp_data = json.load(f)
                        
                        count = 0
                        for name, data in imp_data.items():
                            final_name = name
                            if final_name in batch_manager.profiles:
                                final_name = name + "_imported_" + time.strftime("%H%M%S")
                            batch_manager.profiles[final_name] = data
                            count += 1
                        batch_manager.save_profiles()
                        print("✅ Successfully imported {0} profiles.".format(count))
                except Exception as e:
                    print("❌ Import failed: {0}".format(e))
                continue
        try:
            sel = int(choice) - 1
            if 0 <= sel < len(profile_names):
                p_name = profile_names[sel]
                print("\nEditing: '{}'".format(p_name))
                print("[1] Add Students")
                print("[2] Remove Students")
                print("[3] Delete Profile")
                print("[4] Rename Profile")
                print("[5] Export One/More Profiles")
                print("[6] Import Profiles from File")
                print("[7] Update Profile (Rescan Names/Sessions)")
                print("[b] Cancel")
                act = input_func("Choice: ").strip()
                if act == '1':
                    print("\n--- Discovery Mode: Add New Students ---")
                    # Step 1: Input Session and Ranges
                    p_data = batch_manager.profiles[p_name]
                    saved_pro_id = p_data.get("pro_id")
                    
                    if saved_pro_id and saved_pro_id in programs:
                        pro_id = saved_pro_id
                        print("Auto-Matched Program: {}".format(programs[pro_id]))
                    else:
                        r = prompt_preloaded_program(programs)
                        if r[0] == 'b': continue
                        pro_id = r[0]
                        batch_manager.update_batch_info(p_name, pro_id=pro_id)

                    # Range inputs
                    s_res = prompt_custom_session(sessions, "Main Batch Session")
                    if s_res[0] == 'b': continue
                    mb_sess_id = s_res[0]
                    r_str = input_func("Range(s): ").strip()
                    if r_str.lower() == 'b': continue
                    mb_regs = parse_range(r_str)
                    
                    ra_tasks = []
                    while True:
                        print("\nAdditional Re-adds (Current: {})".format(len(ra_tasks)))
                        r_str = input_func("Range (or Enter to scan): ").strip()
                        if r_str.lower() == 'b': break
                        if not r_str: break
                        nr = parse_range(r_str)
                        if not nr: continue
                        ns_res = prompt_custom_session(sessions, "Session")
                        if ns_res[0] == 'b': continue
                        ra_tasks.extend([(r, ns_res[0]) for r in nr])
                    
                    discovery_tasks = [(r, mb_sess_id) for r in mb_regs] + ra_tasks
                    if not discovery_tasks: continue
                    
                    # Step 2: Select Exam to scan against
                    exams_cache = fetch_exams(pro_id)
                    full_sess_str = sessions.get(mb_sess_id, "")
                    e_res = handle_exam_selection(exams_cache, full_sess_str)
                    if e_res[0] == 'b': continue
                    exam_id = e_res[0]
                    
                    # Step 3: Fast Scan
                    print("\nChecking {} students for new entries...".format(len(discovery_tasks)))
                    discovered_items = []
                    found_lock = threading.Lock()
                    
                    def discovery_worker():
                        while True:
                            try:
                                reg, sess = q.get_nowait()
                                retries = 0
                                while retries < 3:
                                    res, _ = fetch_student_result(reg, pro_id, sess, exam_id)
                                    if res == "NETWORK_ERROR":
                                        retries += 1
                                        time.sleep(random.uniform(2.0, 5.0))
                                        continue
                                    if res and isinstance(res, dict) and 'GPA' in res:
                                        with found_lock: discovered_items.append([int(reg), sess, res.get('Name', 'Unknown')])
                                    break
                                q.task_done()
                            except queue.Empty: break
                    
                    q = queue.Queue()
                    for t in discovery_tasks: q.put(t)
                    threads = []
                    for _ in range(min(30, len(discovery_tasks))):
                        thr = threading.Thread(target=discovery_worker); thr.start(); threads.append(thr)
                    for thr in threads: thr.join()
                    
                    # Filtering
                    existing_regs = set()
                    raw_exist = p_data.get("regs", [])
                    for r_item in raw_exist:
                        if isinstance(r_item, list): existing_regs.add(r_item[0])
                        else: existing_regs.add(int(r_item))
                    
                    new_entries = [i for i in discovered_items if i[0] not in existing_regs]
                    
                    if new_entries:
                        batch_manager.add_to_batch(p_name, new_entries)
                        print("✅ Discovery complete! Added {} new students.".format(len(new_entries)))
                    else:
                        print("ℹ️ No new students found in these ranges.")
                elif act == '2':
                    print("\n--- Removal Mode ---")
                    print("[1] Manual List Removal")
                    print("[2] Smart Purge Scan (Remove students not found in an Exam)")
                    rem_choice = input_func("Choice [1]: ").strip() or '1'
                    
                    if rem_choice == '1':
                        inp = input_func("List to remove (Range or CSV): ").strip()
                        regs = parse_range(inp)
                        if regs: batch_manager.remove_from_batch(p_name, regs); print("Removed.")
                    elif rem_choice == '2':
                        print("\n--- Smart Purge: Auto-Remove Missing Students ---")
                        p_data = batch_manager.profiles[p_name]
                        saved_pro_id = p_data.get("pro_id")
                        
                        if saved_pro_id and saved_pro_id in programs:
                            pro_id = saved_pro_id
                            print("Auto-Matched Program: {}".format(programs[pro_id]))
                        else:
                            r = prompt_preloaded_program(programs)
                            if r[0] == 'b': continue
                            pro_id = r[0]
                            batch_manager.update_batch_info(p_name, pro_id=pro_id)

                        s_res = prompt_custom_session(sessions, "Purge Scan Session")
                        if s_res[0] == 'b': continue
                        mb_sess_id = s_res[0]
                        r_str = input_func("Range(s) to check: ").strip()
                        if r_str.lower() == 'b': continue
                        mb_regs = parse_range(r_str)
                        
                        ra_tasks = []
                        while True:
                            print("\nAdditional Ranges (Current: {})".format(len(ra_tasks)))
                            r_str = input_func("Range (or Enter to scan): ").strip()
                            if r_str.lower() == 'b': break
                            if not r_str: break
                            nr = parse_range(r_str)
                            if not nr: continue
                            ns_res = prompt_custom_session(sessions, "Session")
                            if ns_res[0] == 'b': continue
                            ra_tasks.extend([(r, ns_res[0]) for r in nr])
                        
                        purge_tasks = [(r, mb_sess_id) for r in mb_regs] + ra_tasks
                        if not purge_tasks: continue
                        
                        exams_cache = fetch_exams(pro_id)
                        full_sess_str = sessions.get(mb_sess_id, "")
                        e_res = handle_exam_selection(exams_cache, full_sess_str)
                        if e_res[0] == 'b': continue
                        exam_id = e_res[0]
                        
                        print("\nVerifying {} students for purge...".format(len(purge_tasks)))
                        missing_regs = []
                        missing_lock = threading.Lock()
                        
                        def purge_worker():
                            while True:
                                try:
                                    reg, sess = q.get_nowait()
                                    retries = 0
                                    while retries < 3:
                                        res, _ = fetch_student_result(reg, pro_id, sess, exam_id)
                                        if res == "NETWORK_ERROR" or res is None:
                                            retries += 1
                                            time.sleep(random.uniform(2.0, 5.0))
                                            continue
                                        # Fix: Only purge if definitively 'NOT_FOUND'
                                        if res == "NOT_FOUND":
                                            with missing_lock: missing_regs.append(int(reg))
                                        break
                                    q.task_done()
                                except queue.Empty: break
                        
                        q = queue.Queue()
                        for t in purge_tasks: q.put(t)
                        threads = []
                        for _ in range(min(30, len(purge_tasks))):
                            thr = threading.Thread(target=purge_worker)
                            thr.start(); threads.append(thr)
                        for thr in threads: thr.join()
                        if missing_regs:
                            raw_regs = p_data.get("regs", [])
                            if raw_regs and isinstance(raw_regs[0], (list, tuple)):
                                batch_regs = set([item[0] for item in raw_regs])
                            else:
                                batch_regs = set(raw_regs)
                                
                            overlap = [r for r in missing_regs if r in batch_regs]
                            if not overlap:
                                print("\nPurge Impact: None.")
                            else:
                                print("\n[ Purge Impact: {} students ]".format(len(overlap)))
                                if input_func("Type 'PURGE': ").strip() == 'PURGE':
                                    batch_manager.remove_from_batch(p_name, overlap)
                                    print("✅ Successfully purged.")
                                else: print("Cancelled.")
                        else:
                            print("ℹ️ All students in these ranges participated in the exam. Nothing to remove.")
                elif act == '3':
                    if input_func("Type 'DELETE': ").strip() == 'DELETE':
                        batch_manager.delete_batch(p_name); print("Deleted.")
                elif act == '4':
                    nn = input_func("New name: ").strip()
                    if nn:
                        batch_manager.profiles[nn] = batch_manager.profiles.pop(p_name)
                        batch_manager.save_profiles()
                        print("Renamed.")
                elif act == '7':
                    print("\n--- Update Profile: Rescan Names & Sessions ---")
                    p_data = batch_manager.profiles[p_name]
                    current_regs = p_data.get("regs", [])
                    if not current_regs:
                        print("Profile is empty."); continue
                        
                    saved_pro_id = p_data.get("pro_id")
                    if saved_pro_id and saved_pro_id in programs:
                        pro_id = saved_pro_id
                        print("Auto-Matched Program: {}".format(programs[pro_id]))
                    else:
                        r = prompt_preloaded_program(programs)
                        if r[0] == 'b': continue
                        pro_id = r[0]
                        batch_manager.update_batch_info(p_name, pro_id=pro_id)
                    
                    exams_cache = fetch_exams(pro_id)
                    profile_sess_name = "Any"
                    saved_sess_id = p_data.get("sess_id")
                    if saved_sess_id and saved_sess_id in sessions:
                        profile_sess_name = sessions[saved_sess_id]
                    
                    e_res = handle_exam_selection(exams_cache, profile_sess_name)
                    if e_res[0] == 'b': continue
                    exam_id = e_res[0]
                    
                    scan_tasks = []
                    for item in current_regs:
                        if isinstance(item, list):
                            reg = item[0]
                            sess = item[1]
                            name = item[2] if len(item) > 2 else "Unknown"
                            scan_tasks.append((reg, sess, name))
                        else:
                            scan_tasks.append((item, "AUTO", "Unknown"))
                    
                    print("\nRescanning {} students...".format(len(scan_tasks)))
                    updated_results = []
                    res_lock = threading.Lock()
                    
                    def rescan_worker():
                        global last_successful_session, global_backoff_until
                        while True:
                            try:
                                reg, sess, old_name = q.get_nowait()
                                
                                # Natural jitter
                                time.sleep(random.uniform(0.1, 0.5))
                                
                                # Adaptive Jitter/Backoff check
                                with get_stealth_lock():
                                    if time.time() < global_backoff_until:
                                        time.sleep(random.uniform(3.0, 7.0))
                                
                                sessions_to_try = [sess]
                                if sess == "AUTO":
                                    sessions_to_try = []
                                    with get_stealth_lock():
                                        if last_successful_session:
                                            sessions_to_try.append(last_successful_session)
                                    
                                    if sessions:
                                        all_ids = sorted(list(sessions.keys()), reverse=True)
                                        sessions_to_try.extend([s for s in all_ids if s not in sessions_to_try])
                                
                                found_res = None
                                for s in sessions_to_try:
                                    retries = 0
                                    while retries < 3:
                                        # Global backoff check within retry loop
                                        if time.time() < global_backoff_until:
                                            time.sleep(random.uniform(2.0, 5.0))
                                            
                                        res, _ = fetch_student_result(reg, pro_id, s, exam_id)
                                        
                                        if res == "NETWORK_ERROR":
                                            retries += 1
                                            with get_stealth_lock():
                                                global_backoff_until = time.time() + 15.0
                                            time.sleep(random.uniform(10.0, 15.0))
                                            continue
                                            
                                        if res and isinstance(res, dict):
                                            found_res = [int(reg), res.get('_sess_id', s), res.get('Name', old_name)]
                                            # Update Session Pin
                                            if sess == "AUTO":
                                                with get_stealth_lock():
                                                    last_successful_session = s
                                        break
                                    if found_res: break
                                    
                                with res_lock:
                                    if found_res: updated_results.append(found_res)
                                    else: updated_results.append([int(reg), sess, old_name])
                                q.task_done()
                            except queue.Empty: break
                    
                    q = queue.Queue()
                    for t in scan_tasks: q.put(t)
                    
                    # Concurrency Control: Restored to 15 threads
                    thread_count = min(15, len(scan_tasks))
                    threads = []
                    for _ in range(thread_count):
                        thr = threading.Thread(target=rescan_worker); thr.start(); threads.append(thr)
                    for thr in threads: thr.join()
                    
                    if updated_results:
                        batch_manager.profiles[p_name]["regs"] = sorted(updated_results, key=lambda x: x[0])
                        batch_manager.save_profiles()
                        print("✅ Process complete! Updated names/sessions for {} students.".format(len(updated_results)))
                elif act == '5':
                    # Export Logic
                    print("\n--- Export Profiles ---")
                    print("[1] Export THIS profile ('{}')".format(p_name))
                    print("[2] Export ALL profiles")
                    print("[3] Select multiple profiles to export")
                    ex_choice = input_func("Choice [1]: ").strip() or '1'
                    
                    to_export = {}
                    if ex_choice == '1':
                        to_export[p_name] = batch_manager.profiles[p_name]
                    elif ex_choice == '2':
                        to_export = batch_manager.profiles
                    elif ex_choice == '3':
                        print("\nAvailable Profiles:")
                        p_list = sorted(list(batch_manager.profiles.keys()))
                        for i, n in enumerate(p_list, 1):
                            print("[{}] {}".format(i, n))
                        idx_str = input_func("Enter numbers (e.g. 1,3,5-7): ").strip()
                        idxs = parse_range(idx_str)
                        for idx in idxs:
                            if 1 <= idx <= len(p_list):
                                name = p_list[idx-1]
                                to_export[name] = batch_manager.profiles[name]
                    
                    if to_export:
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        fname = "ducmc_export_{}.json".format(ts)
                        downloads_dir = "/storage/emulated/0/Download"
                        export_dir = downloads_dir if os.path.exists(downloads_dir) else SCRIPT_DIR
                        fpath = os.path.join(export_dir, fname)
                        try:
                            with open(fpath, 'w', encoding='utf-8') as f:
                                json.dump(to_export, f, indent=4)
                            print("✅ Exported {} profiles to: {}".format(len(to_export), fpath))
                        except Exception as e:
                            print("❌ Export failed: {}".format(e))
                
                elif act == '6':
                    print("This option is now at the top level menu.")
        except ValueError:
            pass

def hidden_menu_handler(programs, sessions):
    print("\n" + "="*40)
    print("             🌟 ACADEMIC TRANSCRIPT 🌟")
    print("="*40)
    
    if not batch_manager.profiles:
        print("❌ No profiles found. Capture some results first!"); return
        
    p_names = sorted(list(batch_manager.profiles.keys()))
    for i, n in enumerate(p_names, 1):
        print("[{}] {}".format(i, n))
    
    try:
        c_str = input_func("Select Profile: ").strip()
        if not c_str: return
        choice = int(c_str) - 1
        if not (0 <= choice < len(p_names)): return
        p_name = p_names[choice]
        p_data = batch_manager.profiles[p_name]
        pro_id = p_data.get("pro_id")
        
        if not pro_id:
            res = prompt_preloaded_program(programs)
            if res[0] == 'b': return
            pro_id = res[0]
            batch_manager.update_batch_info(p_name, pro_id=pro_id)

        raw_regs = p_data.get("regs", [])
        if not raw_regs: print("Profile is empty."); return
        
        formatted = []
        for item in raw_regs:
            if not isinstance(item, list): formatted.append([int(item), "AUTO", "Unknown"])
            elif len(item) == 2: formatted.append([int(item[0]), item[1], "Unknown"])
            else: formatted.append([int(item[0]), item[1], item[2]])
            
        # Determine main session (Priority: saved sess_id > most frequent)
        profile_main_sess = p_data.get("sess_id")
        if profile_main_sess and profile_main_sess in sessions:
            main_sess = profile_main_sess
        else:
            sess_counts = collections.Counter([x[1] for x in formatted if x[1] != "AUTO"])
            main_sess = sess_counts.most_common(1)[0][0] if sess_counts else "AUTO"
        
        main_batch = sorted([x for x in formatted if x[1] == main_sess or x[1] == "AUTO"], key=lambda x: x[0])
        readds = sorted([x for x in formatted if x[1] != main_sess and x[1] != "AUTO"], key=lambda x: (x[1], x[0]))
        all_sorted = main_batch + readds
        
        print("\n--- Student Directory [{}] ---".format(p_name))
        for i, (r, s, n) in enumerate(all_sorted, 1):
            s_str = str(s)
            ms_str = str(main_sess)
            if s_str == ms_str or s_str == "AUTO":
                tag = "[Main]"
            else:
                s_name = sessions.get(s_str, s_str)
                # Extract year (e.g., 2021-2022 -> 21)
                y_match = re.search(r"20(\d{2})", s_name)
                y_suffix = y_match.group(1) if y_match else s_str
                tag = "[Readd:{}]".format(y_suffix)
                
            print("{:2}. {:20} (Reg: {}) {}".format(i, n[:20], r, tag))
            
        s_choice = int(input_func("\nSelect Student: ").strip()) - 1
        if not (0 <= s_choice < len(all_sorted)): return
        
        target_student = all_sorted[s_choice]
        reg_no, sess_id, st_name = target_student
        
        print("\n--- Options for {} ---".format(st_name))
        print("[1] Single Semester Result")
        print("[2] Full Academic History (Exhaustive)")
        opt = input_func("Choice [1]: ").strip() or '1'
        
        exams_cache = fetch_exams(pro_id)
        
        if opt == '1':
            e_res = handle_exam_selection(exams_cache, sessions.get(sess_id, ""))
            if e_res[0] == 'b': return
            exam_id, exam_name = e_res[0], e_res[1]
            
            print("\n🔍 Scanning for {}...".format(st_name))
            res, _ = fetch_student_result(reg_no, pro_id, sess_id, exam_id)
            if not res or res == "NETWORK_ERROR" or res == "NOT_FOUND":
                print("❌ Not found."); return
            generate_transcript_report([res], exam_name, st_name)
            
        elif opt == '2':
            print("\n⏳ Exhaustive Scan... (May take 1 min)")
            history = []
            all_exam_ids = sorted(list(exams_cache.keys()), reverse=True)
            q = queue.Queue()
            for eid in all_exam_ids: q.put(eid)
            h_lock = threading.Lock()
            def history_worker():
                while True:
                    try: eid = q.get_nowait()
                    except queue.Empty: break
                    
                    # Jitter
                    time.sleep(random.uniform(0.1, 0.4))
                    
                    s_to_try = [sess_id] if sess_id != "AUTO" else sorted(list(sessions.keys()), reverse=True)
                    for tsid in s_to_try:
                        time.sleep(random.uniform(0.05, 0.15))
                        res, _ = fetch_student_result(reg_no, pro_id, tsid, eid)
                        if res and isinstance(res, dict) and (res.get('GPA', res.get('SGPA', '-')) != '-' or res.get('Subjects')):
                            with h_lock:
                                res['_exam_name'] = exams_cache[eid]
                                history.append(res)
                            break
                    print(".", end="", flush=True)
            threads = []
            for _ in range(15):
                t = threading.Thread(target=history_worker)
                t.daemon = True; t.start(); threads.append(t)
            for t in threads: t.join()
            
            if not history: print("\n❌ No history found."); return
            history.sort(key=lambda x: str(x.get('_exam_name', '')), reverse=False)
            print("\n✅ Found {} records.".format(len(history)))
            generate_transcript_report(history, "Academic History", st_name)
            
    except Exception as e:
        print("Error: {}".format(e))
        return
            
def generate_transcript_report(records, title, name, return_html=False):
    css = """
    :root { 
        --bg: #111827; --text: #f3f4f6; --card: #1f2937; --border: #374151; 
        --primary: #3b82f6; --accent: #60a5fa; --header: #374151;
    }
    #cli-transcript-root { background-color: var(--bg); color: var(--text); padding: 25px; font-family: 'Outfit', sans-serif; min-height: 100vh; }
    #cli-transcript-root .header-card { background: var(--card); padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 25px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); max-width: 900px; margin-left: auto; margin-right: auto; }
    #cli-transcript-root h2 { margin: 0 0 10px 0; font-size: 1.2em; color: var(--primary); }
    #cli-transcript-root p { margin: 0; font-size: 1em; color: var(--text); opacity: 0.9; }
    #cli-transcript-root .exam-block { background: var(--card); border: 1px solid var(--border); border-left: 5px solid var(--primary); border-radius: 6px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); max-width: 900px; margin-left: auto; margin-right: auto; overflow: hidden; }
    #cli-transcript-root .exam-title { color: var(--accent); padding: 15px 20px; font-weight: 600; font-size: 0.95em; margin: 0; background: var(--header); }
    #cli-transcript-root table { width: 100%; border-collapse: collapse; }
    #cli-transcript-root th, #cli-transcript-root td { padding: 12px 20px; text-align: left; }
    #cli-transcript-root th { background: var(--header); color: var(--text); font-weight: 700; font-size: 0.85em; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); opacity: 0.8; }
    #cli-transcript-root td { border-bottom: 1px solid var(--border); font-size: 0.9em; color: var(--text); }
    #cli-transcript-root .summary { background: var(--header); padding: 12px 20px; font-weight: 600; color: var(--text); font-size: 0.9em; border-top: 1px solid var(--border); border-radius: 0 0 6px 6px; display: flex; gap: 5px;}
    """
    # CSS Prefixing for Dashboard Injection
    css_wrapped = "<div id='cli-transcript-root'><style>" + css + "</style>"
    
    # Header Section
    reg_val = records[0].get('Registration No', '-') if records else '-'
    html = css_wrapped + "<div class='header-card'><h2>&#127775; Student Record</h2><p><b>" + str(name) + "</b> (Reg: " + str(reg_val) + ")</p></div>"

    for r in records:
        html += "<div class='exam-block'>"
        
        exam_name_parsed = r.get('_exam_name', title)
        html += "<div class='exam-title'>&#128197; {}</div>".format(exam_name_parsed)
        
        if r.get('Subjects'):
            html += "<table><thead><tr><th>Code</th><th>Subject</th><th>Grade</th><th>GP</th></tr></thead><tbody>"
            for s in r['Subjects']:
                html += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(s.get('code','-'), s['name'], s['grade'], s['gp'])
            html += "</tbody></table>"
            
        e_name = r.get('_exam_name', '').lower()
        is_extra = any(x in e_name for x in ["retake", "improvement", "clearance", "special", "junior"])
        
        if not is_extra:
            html += "<div class='summary'>"
            html += "Result: {} | GPA: {} | CGPA: {}".format(r.get('Overall Result', '-'), r.get('GPA', r.get('SGPA', '-')), r.get('CGPA', '-'))
            html += "</div>"
        html += "</div>"
        
    html += "</div>" # Close cli-transcript-root
    if return_html: return html
    
    # Wrap in standard HTML for saving to file
    html_file = f"<html><head><meta charset='utf-8'><title>Student Record - {name}</title></head><body>{html}</body></html>"

    fname = "Student_Record_{}_{}.html".format(name.replace(" ", "_"), time.strftime("%H%M%S"))
    downloads_dir = "/storage/emulated/0/Download"
    fpath = os.path.join(downloads_dir if os.path.exists(downloads_dir) else SCRIPT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f: f.write(html_file)
    print("\n✅ Document saved: {}".format(fpath))
    
    try:
        os.chdir(os.path.dirname(fpath))
        import http.server, socketserver
        class SilentH(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args): pass
        server = socketserver.TCPServer(("0.0.0.0", 0), SilentH)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        # Resilient Viewer using native webbrowser (best for Pydroid 3)
        url = "http://localhost:{}/{}".format(port, urllib_parse.quote(os.path.basename(fpath)))
        print("\n🔗 Web Viewer active at: {}".format(url))
        print("💡 If it doesn't open automatically, you can open it manually from your Downloads folder.")
        
        # Give the server thread a moment to bind
        time.sleep(0.5)
        
        try: 
            import webbrowser
            # On Android, webbrowser.open can sometimes be finicky 
            # if called too soon or with localhost vs 127.0.0.1
            webbrowser.open(url)
        except:
            # Fallback to am start if webbrowser fails
            try:
                with open(os.devnull, 'w') as fnull:
                    subprocess.call(["am", "start", "--user", "0", "-a", "android.intent.action.VIEW", "-t", "text/html", "-d", url], stdout=fnull, stderr=fnull)
            except: pass
            
        input_func("\nPress Enter to stop viewer...")
        server.shutdown()
        os.chdir(ORIGINAL_DIR)
    except: pass

def create_manual_batch(programs, sessions):
    """Creates a provisional batch using standard naming convention."""
    print("\n=== Create Manual Batch (Provisional) ===")
    print("Creates a batch WITHOUT portal contact.")
    print("Auto-promoted when results are published.\n")
    
    # 1. Program selection (reuse existing prompt)
    res = prompt_preloaded_program(programs)
    if res[0] == 'b': return
    pro_id, pro_name = res
    
    # 2. Session selection
    s_res = prompt_custom_session(sessions, "Batch Session")
    if s_res[0] == 'b': return
    sess_id = s_res[0]
    
    # 3. Registration range
    r_str = input_func("Registration Range(s): ").strip()
    if r_str.lower() == 'b': return
    regs = parse_range(r_str)
    if not regs:
        print("❌ Invalid range.")
        return
    regs = list(dict.fromkeys(regs))
    
    # 4. Profile name — enforce standard naming convention
    import database as db
    while True:
        p_name = input_func("Batch Profile Name (e.g. 'cse 12'): ").strip()
        if not p_name: return
        # Validate format: dept_prefix + space + batch_number
        parts = p_name.lower().split()
        is_valid_format = False
        if len(parts) >= 2 and parts[0] in ('cse', 'eee', 'civil'):
            try:
                int(parts[1])
                is_valid_format = True
            except ValueError:
                pass
        
        if not is_valid_format:
            print("❌ Must follow format: 'cse 12', 'eee 12', 'civil 12'")
            continue
        
        if db.profile_exists(p_name.lower().strip()):
            print("Profile already exists")
            continue
        break
    
    # 5. Save to SQLite (V2 branch)
    db.save_provisional_profile(p_name, pro_id, sess_id, [(r,) for r in regs])
    
    # 6. Save to saved_profiles.json (Main branch)
    batch_manager.save_provisional_to_json(p_name, pro_id, sess_id, regs)
    
    print(f"\n✅ Provisional batch '{p_name}' created with {len(regs)} students.")
    print("   Names: 'Unknown' (auto-populated when results are published)")
    print("   Readds: Auto-detected from senior batches on first exam scan")
    print("   Promotion: Automatic when exam monitor detects published results")

def main():
    print("Welcome tob FEC result finder")
    programs, sessions = fetch_programs_and_sessions()
    if not programs or not sessions: print("Connectivity error: Please check your internet connection."); return
        
    state, pro_id, pro_name = 0, None, None
    exam_id, exam_name = None, None
    mb_regs, mb_sess_id = [], None
    ra_tasks = []
    exams_cache = {}
    tasks = []
    active_profile_name = None
    target_college = "faridpur engineering college"

    while state < 7:
        if state == 0:
            print("\n--- Primary Input Source ---")
            print("[1] Manual ID Ranges")
            print("[2] Load Saved Batch Profile")
            p_count = len(batch_manager.profiles)
            print("    - Found {0} profiles.".format(p_count))
            print("[3] Manage Saved Profiles (Update / Delete / Export)")
            print("[4] Create Manual Batch (No Portal Required)")
            choice = input_func("Choice [1]: ").strip()
            if not choice:
                state = 1
            elif choice == '!':
                hidden_menu_handler(programs, sessions)
                continue
            elif choice == '1':
                state = 1
            elif choice == '2':
                if not batch_manager.profiles: print("No profiles found."); continue
                # List profiles
                p_names = sorted(list(batch_manager.profiles.keys()))
                for i, n in enumerate(p_names, 1):
                    p_reg_count = len(batch_manager.profiles[n].get("regs", []))
                    print("[{}] {} ({} students)".format(i, n, p_reg_count))
                sel = input_func("Select: ").strip()
                if sel.lower() == 'b': continue
                try:
                    idx = int(sel) - 1
                    if 0 <= idx < len(p_names):
                        active_profile_name = p_names[idx]
                        p_data = batch_manager.profiles[active_profile_name]
                        pro_id = p_data.get("pro_id")
                        mb_regs_raw = p_data.get("regs", [])
                        tasks = []
                        for item in mb_regs_raw:
                            if isinstance(item, list): tasks.append((item[0], item[1]))
                            else: tasks.append((item, "AUTO"))
                        
                        if pro_id:
                            print("\nAuto-Loading Program: {}".format(programs.get(pro_id, pro_id)))
                            mb_sess_id = p_data.get("sess_id")
                            
                            # Use ONLY 'Main' students for the probe verification (strict)
                            probe_regs = [int(r[0]) for r in mb_regs_raw if str(r[1]) == str(mb_sess_id)][:5]
                            
                            # Full list for task scanning
                            mb_regs = []
                            for item in mb_regs_raw:
                                if isinstance(item, list): mb_regs.append(int(item[0]))
                                else: mb_regs.append(int(item))
                            
                            exams_cache = fetch_exams(pro_id)
                            state = 5
                        else: state = 1
                except: pass
            elif choice == '3': manage_profiles(programs, sessions); continue
            elif choice == '4': create_manual_batch(programs, sessions); continue
            else: state = 1
                   
        elif state == 1: # Program
            res = prompt_preloaded_program(programs)
            if res[0] == 'b': state = 0; continue
            pro_id, pro_name = res
            exams_cache = fetch_exams(pro_id)
            state = 2
            
        elif state == 2: # Main Session & Range
            s_res = prompt_custom_session(sessions, "Main Batch Session")
            if s_res[0] == 'b': state = 1; continue
            mb_sess_id = s_res[0]
            r_str = input_func("Range(s): ").strip()
            if r_str.lower() == 'b': state = 1; continue
            mb_regs = parse_range(r_str)
            if not mb_regs: continue
            if active_profile_name: batch_manager.update_batch_info(active_profile_name, sess_id=mb_sess_id)
            state = 3
            
        elif state == 3: # Re-add Loop
            print("\n--- Additional Re-adds (Total: {}) ---".format(len(mb_regs) + len(ra_tasks)))
            r_str = input_func("Range (or Enter): ").strip()
            if r_str.lower() == 'b': ra_tasks = []; state = 2; continue
            if not r_str:
                tasks = [(r, mb_sess_id) for r in mb_regs] + ra_tasks
                state = 5; continue
            nr = parse_range(r_str)
            if not nr: continue
            ns_res = prompt_custom_session(sessions, "Session")
            if ns_res[0] == 'b': continue
            ra_tasks.extend([(r, ns_res[0]) for r in nr])
            
        elif state == 5: # Categorized Selection
            full_sess_str = sessions.get(mb_sess_id, "")
            e_res = handle_exam_selection(exams_cache, full_sess_str, probe_regs, pro_id)
            if e_res[0] == 'b': state = 0; continue
            exam_id, exam_name = e_res[0], e_res[1]
            state = 7

    if not tasks: return

    # Synchronization primitives for multi-threading
    results_lock = threading.Lock()
    print_lock = threading.Lock()
    completed_tasks = [0]
    all_results = []
    print("\nScanning {0} students (Optimized Safe Mode)...".format(len(tasks)))
            
    task_queue = queue.Queue()
    for t in tasks: task_queue.put(t)
    num_threads = min(5, len(tasks))
    
    threads = []
    for _ in range(num_threads):
        # Micro-stagger for startup
        time.sleep(random.uniform(0.05, 0.15))
        t = threading.Thread(target=worker_thread, args=(task_queue, pro_id, exam_id, all_results, results_lock, print_lock, len(tasks), completed_tasks, target_college, sessions))
        t.daemon = True; t.start(); threads.append(t)
    for t in threads: t.join()
    
    if not all_results:
        print("\n❌ No results found. (No profile to save)")
        return
    
    clean_exam_name = "".join([c if c.isalnum() else "_" for c in str(exam_name)])[:50]
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    fname = "Results_{0}_{1}.html".format(clean_exam_name, timestamp)
    downloads_dir = "/storage/emulated/0/Download"
    fpath = os.path.join(downloads_dir if os.path.exists(downloads_dir) else SCRIPT_DIR, fname)
    
    with open(fpath, "w", encoding="utf-8") as f: f.write(generate_html_report(all_results, exam_name))
    print("\n✅ Saved to: {0}".format(fpath))
    
    server_running = False
    print("\n🚀 Opening in browser...")
    try:
        # Change to the report directory ONLY for the server scope
        os.chdir(os.path.dirname(fpath))
        import http.server, socketserver
        class SilentHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args): pass
            def do_GET(self):
                # Robustness: If they access root '/' or the filename is slightly off, serve the report
                if self.path == '/' or self.path == '/{}'.format(urllib_parse.quote(fname)):
                    self.path = '/{}'.format(fname)
                return super().do_GET()
        class CustomTCPServer(socketserver.TCPServer): allow_reuse_address = True
        
        # Bind to 0.0.0.0 for maximum compatibility in mobile networks
        server = CustomTCPServer(("0.0.0.0", 0), SilentHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever)
        t.daemon = True
        t.start()
        server_running = True
        
        # Use 127.0.0.1 for the actual URL to ensure it stays local
        http_url = "http://127.0.0.1:{}/{}".format(port, urllib_parse.quote(fname))
        try:
            subprocess.check_call(["am", "start", "-a", "android.intent.action.VIEW", "-d", http_url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except:
            import webbrowser
            webbrowser.open(http_url)
    except Exception as e:
        print("⚠️ Could not auto-launch ({0}).".format(e))
    # Finally removed from here to prevent premature directory change
    
    # Profile Saving (Manual mode only)
    if all_results and not active_profile_name:
        regs_with_metadata = []
        for r in all_results:
            regs_with_metadata.append([int(r['Registration No']), r.get('_sess_id', 'AUTO'), r.get('Name', 'Unknown')])
            
        print("\n--- Batch Profile Management ---")
        p_name = input_func("Save these as profile? (Enter name or skip): ").strip()
        if p_name:
            batch_manager.save_new_batch(p_name, regs_with_metadata, pro_id=pro_id, latest_exam_id=exam_id)
            print("✅ Profile '{}' saved successfully with student names.".format(p_name))

    if server_running:
        print("\n" + "="*40)
        print("🖥️  Report server is active on port {0}.".format(port))
        print("🔗 URL: http://127.0.0.1:{0}".format(port))
        print("="*40)
        try:
            input_func("\nPress Enter to shutdown server and exit...")
        finally:
            # ALWAYS return back to original directory AFTER server is done
            os.chdir(ORIGINAL_DIR)

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print("\n❌ Error: {0}.".format(e))
        input_func("\nPress Enter to exit...")
