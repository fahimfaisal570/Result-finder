from .network import *
from .profiles import meta_cache
import re
import time
import random
import collections
import threading
import sys
if sys.version_info[0] < 3: import Queue as queue
else: import queue

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
    # Always ensure a session handshake (visit BASE_URL) if cookies are missing.
    # This prevents the portal from blocking session-less AJAX requests after a few attempts.
    if not SESSION_COOKIES:
        make_request(BASE_URL)

    cached_progs, cached_sess = meta_cache.get_cache()
    if cached_progs and cached_sess:
        PROGRAMS_CACHE.update(cached_progs)
        SESSIONS_CACHE.update(cached_sess)
        return collections.OrderedDict(cached_progs), collections.OrderedDict(cached_sess)

    html = make_request("https://ducmc.du.ac.bd/result.php")
    if not html: 
        print("[!] Failed to connect to {} - Check your internet.".format("result.php"))
        return collections.OrderedDict(), collections.OrderedDict()
    
    programs = collections.OrderedDict()
    sessions = collections.OrderedDict()
    categories = []
    
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
                
    # Parallelize category crawl for programs
    if categories:
        print("[*] Pre-loading programs from {} categories...".format(len(categories)))
        prog_lock = threading.Lock()
        def fetch_cat_progs(cat_id):
            cat_url = "{0}ajax/get_program_by_course.php?course_id={1}".format(BASE_URL, cat_id)
            cat_html = make_request(cat_url)
            if cat_html:
                p_opts = extract_options_from_html(cat_html)
                with prog_lock:
                    for p_val, p_text in p_opts:
                        if p_val != "0": programs[p_val] = p_text

        threads = []
        for cat_id in categories:
            t = threading.Thread(target=fetch_cat_progs, args=(cat_id,))
            t.daemon = True; t.start(); threads.append(t)
        for t in threads: t.join()
        
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
        meta_cache.set_cache(dict(programs), dict(sessions))
    
    PROGRAMS_CACHE.update(programs)
    SESSIONS_CACHE.update(sessions)
    return programs, sessions

def fetch_exams(pro_id):
    url = "{0}?program_id={1}&pedata=99".format(AJAX_URL, pro_id)
    html = make_request(url)
    if not html: return collections.OrderedDict()
    options = extract_options_from_html(html)
    return collections.OrderedDict(options)

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
    # Matches "Result Publication Date" or "Publication Date" followed by any characters until a date DD-MM-YYYY
    # Added non-greedy match for tags and flexible labels
    for pattern in [r"Publication\s*Date.*?(\d{2}-\d{2}-\d{4})", r"Date\s*of\s*Publication.*?(\d{2}-\d{2}-\d{4})"]:
        pub_match = re.search(pattern, html, re.I | re.S)
        if pub_match:
            info['Pub Date'] = pub_match.group(1)
            break
    
    # Resilient Name Matching
    name_match = re.search(r"(?:Student\'?s?\s*)?\bName\b(?!.*College).*?<td[^>]*>\s*(.*?)\s*</td>", html, re.DOTALL | re.IGNORECASE)
    if name_match:
        info['Name'] = re.sub(r'<[^>]*>', '', name_match.group(1)).strip()
    else:
        name_fb = re.search(r"(?:Student\'?s?\s+)?Name\s*[:\-]?\s*<[^>]+>\s*([^<]+)", html, re.IGNORECASE)
        if name_fb: info['Name'] = re.sub(r'<[^>]*>', '', name_fb.group(1)).strip()
        else: return "PARSING_ERROR (Name Not Found)", False
        
    # Aggressive GPA/CGPA Extraction
    # Handles various spacing, casing, and tag variations (e.g. GPA: 3.50, SGPA 3.50, etc)
    gpa_pattern = r'(?:SGPA|GPA|CGPA|YGPA)[^\d]*([\d\.]+)'
    gp_m = re.findall(gpa_pattern, html, re.I)
    if gp_m:
        # First decimal is usually GPA/SGPA, second is CGPA
        info['GPA'] = gp_m[0]
        if len(gp_m) > 1: info['CGPA'] = gp_m[1]
    
    # Fallback search if the label is missing but the result box contains a decimal
    if info['GPA'] == '-':
        # Look for a decimal inside the result div (e.g. Promoted <br> 3.50)
        res_box = re.search(r'font-size:\s*25px;?\'?>(.*?)</div>', html, re.I | re.S)
        if res_box:
            m = re.search(r'([\d\.]+)', res_box.group(1))
            if m: info['GPA'] = m.group(1)
    
    # Overall Result
    res_explicit = re.search(r'(?:Overall\s+)?Result[^\w]*<td[^>]*>(.*?)</td>', html, re.DOTALL | re.IGNORECASE)
    if res_explicit:
        info['Overall Result'] = re.sub(r'<[^>]*>', '', res_explicit.group(1)).strip()
    else:
        status_match = re.search(r'\b(Promoted|Passed|Failed|Withheld|Not Promoted)\b', html, re.IGNORECASE)
        if status_match:
            info['Overall Result'] = status_match.group(1).strip()
            
    # Subject Extraction Logic: Resilient Tag-Agnostic Parser
    subjects = []
    tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    for tr in tr_matches:
        td_matches = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL | re.IGNORECASE)
        if len(td_matches) >= 5:
            serial_raw = re.sub(r'<[^>]*>', '', td_matches[0]).strip()
            if serial_raw.isdigit():
                code = re.sub(r'<[^>]*>', '', td_matches[1]).strip()
                name = re.sub(r'<[^>]*>', '', td_matches[2]).strip()
                grade = re.sub(r'<[^>]*>', '', td_matches[3]).strip()
                gp_raw = re.sub(r'<[^>]*>', '', td_matches[4]).strip()
                gp_match = re.search(r'([\d\.]+)', gp_raw)
                if gp_match:
                    subjects.append({'code': code, 'name': name, 'grade': grade, 'gp': gp_match.group(1)})
    info['Subjects'] = subjects
    
    info['_sess_id'] = sess_id
    return info, is_student_found

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

def classify_exams(exams_dict, batch_session=None, probe_regs=None, pro_id=None):
    """
    Precision Exam Classification System.
    Groups exams into exactly 8 'Main' semester slots and handles retakes/legacy formats.
    """
    mains_slots = {} # slot_idx -> list of [id, name, y, sem, ey, score]
    retakes = collections.OrderedDict()
    if not exams_dict: return collections.OrderedDict(), retakes
    
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
                for pr in probe_regs:
                    res, is_found = fetch_student_result(pr, pro_id, probe_sess_id, cand['id'])
                    if is_found and res:
                        is_valid = True
                        break
                    time.sleep(random.uniform(0.05, 0.1))
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
    
    return mains, retakes

def run_batch_scan_engine(tasks, pro_id, exam_id="0", all_sessions=None, progress_callback=None, target_college="all", num_threads=5):
    """
    Unified CLI-Native scanning engine. 
    Tasks can be (reg, sess) or (reg, sess, exam).
    """
    # Ensure session handshake only if sessions aren't already available
    if not all_sessions:
        fetch_programs_and_sessions()
        
    # Immediate Startup Feedback: Update the UI right now so user knows we are active
    if progress_callback:
        try: progress_callback(0, len(tasks), "Engine firing up... Probing portal.")
        except: pass
    
    # Capture Streamlit context if available
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx, add_report_ctx
        ctx = get_script_run_ctx()
    except ImportError:
        ctx = add_report_ctx = None
    
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
        time.sleep(random.uniform(0.05, 0.15))
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

def worker_thread(task_queue, pro_id, exam_id_default, all_results, results_lock, print_lock, total_tasks, completed_tasks, target_college, all_sessions=None, progress_callback=None):
    while True:
        try: item = task_queue.get_nowait()
        except queue.Empty: break
        
        # Mandatory Human-like initial delay (Jitter) - Synced with CLI for performance
        time.sleep(random.uniform(0.1, 0.4))
        
        # Flex-tasks: (reg, sess) or (reg, sess, exam)
        if len(item) == 3:
            reg_no, sess_id, exam_id = item
        else:
            reg_no, sess_id = item
            exam_id = exam_id_default
        
        sessions_to_try = [sess_id]
        if sess_id == "AUTO" and all_sessions:
            # Shift known successful sessions to front of queue
            hint = SESSION_HINTS.get((pro_id, exam_id))
            all_keys = list(all_sessions.keys())
            if hint and hint in all_keys:
                all_keys.remove(hint)
                sessions_to_try = [hint] + all_keys
            else:
                sessions_to_try = all_keys
            
        student_found_in_any_session = False
        
        for tsid in sessions_to_try:
            # SAFETY JITTER: Restored human-like behavior to satisfy portal rate-limiting
            time.sleep(random.uniform(0.15, 0.4))
            
            if progress_callback:
                try: 
                    # Report granular status so user knows it's NOT stuck
                    progress_callback(completed_tasks[0], total_tasks, "Exam {0}: Checking Session {1}...".format(str(exam_id)[:10], tsid))
                except: pass
            
            retries = 0
            while True:
                # Secondary jitter for retry cycles
                time.sleep(random.uniform(0.1, 0.2))
                res, is_any = fetch_student_result(reg_no, pro_id, tsid, exam_id, target_college)
                if res == "NETWORK_ERROR":
                    retries += 1
                    if retries >= 3:
                        res = None; break
                    # Stabilization delay: Give WAF/Server time to cool down
                    time.sleep(random.uniform(5.0, 10.0))
                    continue
                
                # Robust Discovery Logic: Match GPA or Subjects
                if res and isinstance(res, dict) and (res.get('GPA') != '-' or res.get('Subjects')):
                    student_found_in_any_session = True
                    # Pin session for this batch to optimize subsequent worker lookups
                    if sess_id == "AUTO":
                        SESSION_HINTS[(pro_id, exam_id)] = tsid
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

