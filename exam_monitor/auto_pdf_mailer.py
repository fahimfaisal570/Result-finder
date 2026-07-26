import os
import sys
import json
import smtplib
import re
import threading
# import pdfkit  # Moved inside function for fast-boot optimization
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# Module-level lock to prevent concurrent corruption of shared JSON state files.
# Both saved_profiles.json and v2_sync_tasks.json are read+written during
# multi-department parallel workflow runs, so all writes must be serialised.
_file_write_lock = threading.Lock()

import contextlib
import time

# Cross-process and cross-thread atomic directory lock to prevent JSON state corruption.
# Standard library, zero-dependency, and safe across Windows/Linux OS boundaries.
@contextlib.contextmanager
def file_process_lock(lock_path, timeout=30):
    lock_dir = lock_path + ".lock"
    start_time = time.time()
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            if time.time() - start_time > timeout:
                print(f"Lock acquisition timed out for {lock_path}. Proceeding with fallback to avoid blockages...")
                break
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            if os.path.exists(lock_dir):
                os.rmdir(lock_dir)
        except OSError:
            pass




sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cli_scraper as cs
import database as db

# Department mapping to Github Secrets for Email Routing
DEPT_EMAIL_SECRETS = {
    "12": "CIVIL_HEAD_EMAIL", # Civil Engineering
    "13": "EEE_HEAD_EMAIL",   # EEE
    "14": "CSE_HEAD_EMAIL"    # CSE
}

def identify_batch_for_exam(pro_id, exam_name, exam_id=None):
    """Dynamically finds the appropriate saved profile for an exam via empirical probing.
    Bypasses session jam issues by testing one student from each profile against the portal."""
    if not exam_id: 
        return None, None
        
    profiles = {}
    profiles_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saved_profiles.json")
    if os.path.exists(profiles_path):
        try:
            with open(profiles_path, "r") as f:
                profiles = json.load(f)
        except Exception as e:
            print(f"Error reading saved_profiles.json: {e}")
            profiles = {}
    if not profiles:
        profiles = db.get_profiles()
    if not profiles:
        print("No profiles found in saved_profiles.json or database.")
        return None, None

    # Gather matching profiles
    candidates = {}
    for p_name, p_data in profiles.items():
        if str(p_data.get("pro_id")) == str(pro_id) and len(p_data.get("regs", [])) > 0:
            candidates[p_name] = p_data
            
    if not candidates:
        return None, None
        
    print(f"Probing {len(candidates)} profiles to identify target batch for Exam {exam_id}...")
    cs.fetch_programs_and_sessions()
    
    # Sort candidates by session id descending (newest first) to optimize search
    sorted_candidates = sorted(candidates.items(), key=lambda x: int(x[1].get('sess_id', 0)), reverse=True)
    
    for p_name, p_data in sorted_candidates:
        sess_id = str(p_data.get("sess_id"))
        regs_raw = p_data.get("regs", [])
        
        # Pick up to 5 evenly distributed registration numbers to test
        std_regs = []
        for r in regs_raw:
            if isinstance(r, (list, tuple)):
                std_regs.append(str(r[0]))
            else:
                std_regs.append(str(r))
                
        samples = []
        if std_regs:
            step = max(1, len(std_regs) // 5)
            samples = std_regs[::step][:5]
            
        for test_reg in samples:
            res_data, success = cs.fetch_student_result(test_reg, pro_id, sess_id, exam_id)
            # A profile 'owns' an exam if its students have valid results AND
            # they are taking a full semester (>= 4 subjects).
            if success and isinstance(res_data, dict) and len(res_data.get('Subjects', [])) >= 4:
                print(f"Empirical Match! Profile '{p_name}' owns this exam.")
                return p_name, p_data
                
    print(f"Empirical probe failed. No profiles contain results for this exam.")
    return None, None

def send_pdf_email(dept_name, pro_id, exam_name, pdf_bytes, profile_name):
    smtp_user = os.getenv("EMAIL_USER")
    smtp_pass = os.getenv("EMAIL_PASS")
    admin_receiver = os.getenv("RECEIVER_EMAIL")
    
    head_secret_key = DEPT_EMAIL_SECRETS.get(str(pro_id))
    head_email = os.getenv(head_secret_key) if head_secret_key else None

    if not smtp_user or not smtp_pass or not admin_receiver:
        print("Missing basic SMTP credentials. Cannot send PDF email.")
        return

    subject = f"📊 Official Exam Results: {exam_name}"
    
    body = f"Please find the automated academic results batch report attached.\n\n"
    body += f"Department: {dept_name}\n"
    body += f"Examination: {exam_name}\n"
    body += f"Discovered Batch Profile: {profile_name}\n\n"
    body += "🌐 Quick Access Dashboards:\n"
    body += "• Result Finder: https://fec-result-finder.streamlit.app/\n"
    body += "• Academic Analytics: https://fec-result-analytics.streamlit.app/\n\n"
    body += "This is an automated delivery from the Result Finder monitoring system."
    
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    
    recipients = [admin_receiver]
    if head_email:
        recipients.append(head_email)
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Attach PDF
    pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_attachment.add_header('Content-Disposition', 'attachment', filename=f"{profile_name.replace(' ', '_')}_Results.pdf")
    msg.attach(pdf_attachment)

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg, to_addrs=recipients)
        server.quit()
        print(f"✅ PDF Report sent successfully to {', '.join(recipients)}")
    except Exception as e:
        print(f"❌ Failed to send PDF email: {e}")

# Pre-compiled pattern: captures a department prefix (letters/dots/spaces) and a
# trailing batch number, tolerating any common separators (space, dash, underscore).
_PROFILE_NAME_PAT = re.compile(
    r'^([A-Za-z][A-Za-z.\s]*)\s*[-_]?\s*(\d+)',
    re.IGNORECASE
)

def _parse_profile_parts(name):
    """Return (dept_prefix_str, batch_int) or (None, None) if the name cannot be parsed.

    Handles all common naming formats, e.g.:
        'CSE 15'   -> ('cse', 15)
        'CSE-15'   -> ('cse', 15)
        'EEE_13'   -> ('eee', 13)
        'B.Sc CSE 15' -> ('bsccse', 15)   (dots/spaces stripped from prefix)
    """
    m = _PROFILE_NAME_PAT.match(name.strip())
    if not m:
        return None, None
    # Normalise dept prefix: lower-case, strip dots and internal spaces
    dept = re.sub(r'[^a-z]', '', m.group(1).lower())
    try:
        return dept, int(m.group(2))
    except ValueError:
        return None, None


def _get_senior_profiles_json(profiles, profile_name):
    """Find senior batch profiles from saved_profiles.json (same dept, lower batch#).

    Uses regex-based name parsing so profile names like 'CSE 15', 'CSE-15',
    'EEE_13', or 'B.Sc CSE 15' are all matched correctly regardless of the
    separator or prefix casing used when the profile was created.
    """
    dept_prefix, batch_num = _parse_profile_parts(profile_name)
    if dept_prefix is None:
        print(f"  [Readd] Could not parse department/batch from profile name '{profile_name}'. Skipping senior search.")
        return {}

    senior = {}
    for p_name, p_data in profiles.items():
        p_dept, p_batch = _parse_profile_parts(p_name)
        if p_dept == dept_prefix and p_batch is not None and p_batch < batch_num:
            senior[p_name] = p_data
    return senior


def detect_readds_main_branch(profiles, profile_name, pro_id, exam_id, existing_results, should_save=True):
    """
    Readd detection using subject-overlap fingerprinting.
    Scans senior batch students against the exam. A student is a genuine readd
    only if their subjects significantly overlap with the regular batch's courses.
    This filters out seniors who only took retake/improvement exams.
    """
    # --- Step 1: Build reference subject fingerprint from regular batch ---
    subject_freq = {}
    valid_student_count = 0
    for r in existing_results:
        subjects = r.get('Subjects', [])
        if len(subjects) >= 4:
            valid_student_count += 1
            for s in subjects:
                code = s.get('code', '').strip()
                if code:
                    subject_freq[code] = subject_freq.get(code, 0) + 1

    if valid_student_count == 0:
        print("  [Readd] No regular students with full results to build reference. Skipping.")
        return [], []

    # Reference = subject codes taken by >=30% of valid regular students
    min_freq = max(1, valid_student_count * 0.3)
    reference_codes = {code for code, count in subject_freq.items() if count >= min_freq}

    if not reference_codes:
        print("  [Readd] Could not build reference subject set. Skipping.")
        return [], []

    print(f"  [Readd] Reference fingerprint: {len(reference_codes)} subjects from {valid_student_count} regular students")

    # --- Step 2: Collect existing reg numbers ---
    existing_regs = set()
    p_data = profiles.get(profile_name, {})
    for r in p_data.get("regs", []):
        existing_regs.add(int(r[0]) if isinstance(r, list) else int(r))
    for res in existing_results:
        existing_regs.add(int(res.get('Registration No', res.get('Reg', 0))))

    # --- Step 3: Find & scan senior profiles ---
    senior_profiles = _get_senior_profiles_json(profiles, profile_name)
    if not senior_profiles:
        print(f"  [Readd] No senior batch profiles found for '{profile_name}'.")
        return [], []

    print(f"  [Readd] Scanning {len(senior_profiles)} senior profile(s): "
          f"{', '.join(sorted(senior_profiles.keys()))}")

    scan_tasks = []
    reg_to_source = {}
    for sp_name, sp_data in senior_profiles.items():
        for r in sp_data.get("regs", []):
            if isinstance(r, list):
                reg, sid = int(r[0]), str(r[1])
            else:
                reg, sid = int(r), str(sp_data.get("sess_id", "AUTO"))
            if reg not in existing_regs:
                scan_tasks.append((reg, sid, str(exam_id)))
                reg_to_source[reg] = sp_name
                existing_regs.add(reg)

    if not scan_tasks:
        print("  [Readd] All senior students already accounted for.")
        return [], []

    print(f"  [Readd] Probing {len(scan_tasks)} senior students against exam {exam_id}...")
    readd_results = cs.run_batch_scan_engine(
        tasks=scan_tasks, pro_id=pro_id, exam_id=exam_id,
        target_college="all", num_threads=10
    )

    # --- Step 4: Subject-overlap ghost filter ---
    # A genuine readd takes the SAME courses as the regular batch (high overlap).
    # A retake/improvement student takes DIFFERENT or FEWER courses (low overlap).
    filtered_readds = []
    for r in readd_results:
        subjects = r.get('Subjects', [])
        if len(subjects) < 4:
            continue

        candidate_codes = {s.get('code', '').strip() for s in subjects if s.get('code', '').strip()}
        overlap = candidate_codes & reference_codes
        overlap_ratio = len(overlap) / len(reference_codes) if reference_codes else 0

        reg = r.get('Registration No', r.get('Reg', '?'))
        name = r.get('Name', 'Unknown')

        candidate_subject_count = len(candidate_codes)
        reference_subject_count = len(reference_codes)
        subject_load_ratio = candidate_subject_count / reference_subject_count if reference_subject_count else 0

        if overlap_ratio >= 0.5 and subject_load_ratio >= 0.7:
            filtered_readds.append(r)
            print(f"    [READD] {name} ({reg}) - {len(overlap)}/{len(reference_codes)} subject overlap ({overlap_ratio:.0%})")
        else:
            print(f"    [IMPROVEMENT GUEST / GHOST] {name} ({reg}) - {candidate_subject_count}/{reference_subject_count} subjects ({subject_load_ratio:.0%} load), {overlap_ratio:.0%} overlap -> skipped")

    if not filtered_readds:
        print("  [Readd] No genuine readd students detected after subject-overlap filter.")
        return [], []

    # --- Step 5: Persist readds into saved_profiles.json ---
    readd_info = []
    for res in filtered_readds:
        reg = int(res.get('Registration No', res.get('Reg', 0)))
        name = str(res.get('Name', res.get('Student Name', 'Unknown')))
        sess_id = str(res.get('_sess_id', 'AUTO'))
        source = reg_to_source.get(reg, 'unknown')

        profiles[profile_name].setdefault("regs", []).append([reg, sess_id, name])
        readd_info.append({'reg_no': reg, 'name': name, 'source': source})

    if should_save:
        profiles_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "saved_profiles.json"
        )
        try:
            # Serialise the write using process-safe directory lock
            with file_process_lock(profiles_path):
                with open(profiles_path, "w") as f:
                    json.dump(profiles, f, indent=2)
            print(f"  [Readd] Persisted {len(readd_info)} readd(s) to saved_profiles.json.")
        except Exception as e:
            print(f"  [Readd] WARNING: Failed to persist readds: {e}")

    return filtered_readds, readd_info



def process_and_mail(pro_id, dept_name, exam_id, exam_name):
    print(f"\n--- Initiating Auto-Scan Flow for {exam_name} ---")
    
    profile_name, p_data = identify_batch_for_exam(pro_id, exam_name, exam_id=exam_id)
    if not p_data:
        print(f"No matching automated batch profile found for {exam_name}.")
        return False
        
    print(f"Target Profile Locked: {profile_name}")
    
    regs_raw = p_data.get("regs", [])
    if not regs_raw:
        print("Profile has no students.")
        return False
        
    tasks = []
    sess_id = p_data.get("sess_id")
    for item in regs_raw:
        if isinstance(item, list):
            tasks.append((int(item[0]), str(item[1]), str(exam_id)))
        else:
            tasks.append((int(item), str(sess_id), str(exam_id)))
            
    print(f"Firing up CLI Scraper Engine for {len(tasks)} students...")
    # Initialize the CLI scraper sessions so it has cookies
    cs.fetch_programs_and_sessions()
    
    results = cs.run_batch_scan_engine(
        tasks=tasks,
        pro_id=pro_id,
        exam_id=exam_id,
        target_college="all",
        num_threads=10
    )
    
    if not results:
        print("Scraper yielded no valid results. It might still be uploading.")
        return False
        
    # Filter results to only include students who participated (have subjects)
    results = [r for r in results if r.get('Subjects') and len(r['Subjects']) > 0]
    
    print(f"Filtered to {len(results)} participating students.")

    # --- Readd Detection Phase (Subject-Overlap Fingerprinting) & Promotion ---
    all_profiles = {}
    profiles_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "saved_profiles.json"
    )
    if os.path.exists(profiles_path):
        try:
            with open(profiles_path, "r") as f:
                all_profiles = json.load(f)
        except Exception:
            all_profiles = {}
    if not all_profiles:
        all_profiles = db.get_profiles()

    readd_results, readd_info = detect_readds_main_branch(
        all_profiles, profile_name, pro_id, exam_id, results, should_save=bool(os.path.exists(profiles_path))
    )
    if readd_results:
        results.extend(readd_results)
        print(f"  [Readd] {len(readd_results)} readd student(s) merged into report.")

    if all_profiles.get(profile_name, {}).get("is_provisional"):
        db.promote_provisional_profile(profile_name)
        if os.path.exists(profiles_path):
            all_profiles[profile_name]["is_provisional"] = False
            try:
                with open(profiles_path, "w") as f:
                    json.dump(all_profiles, f, indent=2)
            except Exception as e:
                print(f"  [Promotion] WARNING: Failed to update saved_profiles.json: {e}")
        print(f"  [Promotion] '{profile_name}' promoted from provisional to full.")

    print("Generating Printable Thesis HTML format...")
    # Inject profile_name into title so it appears nicely in the central PDF rendering engine
    full_title = f"Department: {dept_name} | Exam: {exam_name} | Target Batch: {profile_name}"
    html_report = cs.generate_html_report(results, full_title, pro_id=pro_id, sess_id=sess_id)
    
    import pdfkit  # Defer import for fast-boot optimization
    print("📄 Rendering HTML to PDF Format...")
    try:
        # options to ensure CSS renders correctly and fits the page
        options = {
            'page-height': '5000mm', # Force continuous one-page scroll
            'page-width': '230mm',  # Slightly wider for aesthetics
            'margin-top': '0mm',
            'margin-right': '0mm',
            'margin-bottom': '0mm',
            'margin-left': '0mm',
            'encoding': "UTF-8",
            'enable-local-file-access': None,
            'quiet': ''
        }
        pdf_bytes = pdfkit.from_string(html_report, False, options=options)
    except Exception as e:
        print(f"PDF Generation failed: {e}")
        return False
        
    print("Dispatching PDF via Secure Email...")
    send_pdf_email(dept_name, pro_id, exam_name, pdf_bytes, profile_name)
    
    # --- ADDED FOR V2 SYNC CROSS-BRANCH WORKFLOW ---
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sync_file = os.path.join(repo_root, "v2_sync_tasks.json")
    task_data = {
        "pro_id": pro_id,
        "exam_id": exam_id,
        "exam_name": exam_name,
        "profile_name": profile_name
    }
    
    try:
        # Serialise the read-modify-write so parallel department workflow jobs
        # cannot interleave and produce a truncated or duplicate sync task list.
        with file_process_lock(sync_file):
            existing_tasks = []
            if os.path.exists(sync_file):
                with open(sync_file, "r") as f:
                    existing_tasks = json.load(f)
            existing_tasks.append(task_data)
            with open(sync_file, "w") as f:
                json.dump(existing_tasks, f)
        print("Sync task queued for v2 analytics database.")
    except Exception as e:
        print(f"Failed to queue sync task: {e}")
    # -----------------------------------------------

    return True

if __name__ == "__main__":
    # Internal Test execution 
    pass