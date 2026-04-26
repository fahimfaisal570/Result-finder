import os
import sys
import json
import smtplib
import re
# import pdfkit  # Moved inside function for fast-boot optimization
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# Add parent dir to path to import cli_scraper
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cli_scraper as cs

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
        
    profiles_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saved_profiles.json")
    if not os.path.exists(profiles_path):
        print("saved_profiles.json not found")
        return None, None
        
    try:
        with open(profiles_path, "r") as f:
            profiles = json.load(f)
    except Exception as e:
        print(f"Error loading profiles: {e}")
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
        
        # Pick up to 5 evenly distributed standard registration numbers to test
        samples = []
        std_regs = [str(r[0]) for r in regs_raw if isinstance(r, (list, tuple))]
        if std_regs:
            step = max(1, len(std_regs) // 5)
            samples = std_regs[::step][:5]
            
        # Fallback to re-adds if no standard students exist
        if not samples and regs_raw:
            r = regs_raw[0]
            if isinstance(r, list): samples.append(str(r[0]))
            
        for test_reg in samples:
            res_data, success = cs.fetch_student_result(test_reg, pro_id, sess_id, exam_id)
            if success and isinstance(res_data, dict) and len(res_data.get('Subjects', [])) > 0:
                print(f"✅ Empirical Match! Profile '{p_name}' owns this exam.")
                return p_name, p_data
                
    print(f"❌ Empirical probe failed. No profiles contain results for this exam.")
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

def _get_senior_profiles_json(profiles, profile_name):
    """Find senior batch profiles from saved_profiles.json (same dept, lower batch#)."""
    parts = profile_name.lower().split()
    if len(parts) < 2:
        return {}
    dept_prefix = parts[0]
    try:
        batch_num = int(parts[1])
    except ValueError:
        return {}

    senior = {}
    for p_name, p_data in profiles.items():
        p_parts = p_name.lower().split()
        if len(p_parts) >= 2 and p_parts[0] == dept_prefix:
            try:
                p_batch = int(p_parts[1])
                if p_batch < batch_num:
                    senior[p_name] = p_data
            except ValueError:
                continue
    return senior


def detect_readds_main_branch(profiles, profile_name, pro_id, exam_id, existing_results, portal_has_sgpa=True):
    """
    Readd detection for the main branch (saved_profiles.json).
    Scans senior batch students against the exam; if found, adds them
    to the JSON profile and returns the extra results for PDF inclusion.
    """
    # Existing reg nos
    existing_regs = set()
    p_data = profiles.get(profile_name, {})
    for r in p_data.get("regs", []):
        if isinstance(r, list):
            existing_regs.add(int(r[0]))
        else:
            existing_regs.add(int(r))
    for res in existing_results:
        existing_regs.add(int(res.get('Registration No', res.get('Reg', 0))))

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

    # Filter out "ghosts" (Improvement/Retake students).
    # If the portal IS providing SGPAs for regulars, a real re-add MUST also have one.
    # If the portal is missing them globally (e.g. EEE 10/CSE 10 3rd Sem), we relax this.
    filtered_readds = []
    for r in readd_results:
        has_subjects = r.get('Subjects') and len(r['Subjects']) > 0
        has_sgpa = str(r.get('SGPA', '-')) != '-'
        
        if portal_has_sgpa:
            # portal is healthy -> strictly require SGPA to filter ghosts
            # Also require at least 4 subjects to ensure they joined the batch full-time
            if has_subjects and has_sgpa and len(r.get('Subjects', [])) >= 4:
                filtered_readds.append(r)
        else:
            # portal is globally broken -> accept any student with subjects
            # But still require 4 subjects to avoid improvement students in shared IDs
            if has_subjects and len(r.get('Subjects', [])) >= 4:
                filtered_readds.append(r)
    
    readd_results = filtered_readds

    if not readd_results:
        print("  [Readd] No readd students with valid results detected.")
        return [], []

    # Persist readds into saved_profiles.json
    readd_info = []
    for res in readd_results:
        reg = int(res.get('Registration No', res.get('Reg', 0)))
        name = str(res.get('Name', res.get('Student Name', 'Unknown')))
        sess_id = str(res.get('_sess_id', 'AUTO'))
        source = reg_to_source.get(reg, 'unknown')

        # Add to the profile's regs list (as [reg, sess_id, name])
        profiles[profile_name].setdefault("regs", []).append([reg, sess_id, name])

        readd_info.append({'reg_no': reg, 'name': name, 'source': source})
        print(f"    [READD] {name} ({reg}) <- from '{source}'")

    # Write updated profiles back to disk
    profiles_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "saved_profiles.json"
    )
    try:
        with open(profiles_path, "w") as f:
            json.dump(profiles, f, indent=2)
        print(f"  [Readd] Updated saved_profiles.json with {len(readd_info)} readd(s).")
    except Exception as e:
        print(f"  [Readd] WARNING: Failed to persist readds to JSON: {e}")

    return readd_results, readd_info



def process_and_mail(pro_id, dept_name, exam_id, exam_name):
    print(f"\n--- Initiating Auto-Scan Flow for {exam_name} ---")
    
    profile_name, p_data = identify_batch_for_exam(pro_id, exam_name, exam_id=exam_id)
    if not p_data:
        print(f"⚠️ No matching automated batch profile found for {exam_name}.")
        return False
        
    print(f"✅ Target Profile Locked: {profile_name}")
    
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
            
    print(f"🚀 Firing up CLI Scraper Engine for {len(tasks)} students...")
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
        print("❌ Scraper yielded no valid results. It might still be uploading.")
        return False
        
    # Filter results to only include students who participated (have subjects)
    results = [r for r in results if r.get('Subjects') and len(r['Subjects']) > 0]
    
    print(f"✅ Filtered to {len(results)} participating students.")

    # Robust Portal Health Check:
    # We consider the portal "healthy" if regular students (those with >= 4 subjects) have SGPAs.
    # We check the entire batch to ensure ghosts at the top/bottom don't skew the detection.
    portal_has_sgpa = any(
        str(r.get('SGPA', '-')) != '-' 
        for r in results 
        if len(r.get('Subjects', [])) >= 4
    )
    
    if portal_has_sgpa:
        print("ℹ️ Portal is providing SGPAs for this exam. SGPA filter will be active for re-adds.")
    else:
        print("⚠️ Portal is globally missing SGPAs for this exam. Relaxing re-add filter.")

    # --- Readd Detection Phase (Main Branch) ---
    profiles_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "saved_profiles.json"
    )
    with open(profiles_path, "r") as f:
        all_profiles = json.load(f)
        
    readd_results, readd_info = detect_readds_main_branch(
        all_profiles, profile_name, pro_id, exam_id, results, portal_has_sgpa
    )
    if readd_results:
        results.extend(readd_results)
        print(f"  [Readd] {len(readd_results)} readd student(s) merged into report.")

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
        print(f"❌ PDF Generation failed: {e}")
        return False
        
    print("📨 Dispatching PDF via Secure Email...")
    send_pdf_email(dept_name, pro_id, exam_name, pdf_bytes, profile_name)
    
    # --- ADDED FOR V2 SYNC CROSS-BRANCH WORKFLOW ---
    sync_file = "v2_sync_tasks.json"
    task_data = {
        "pro_id": pro_id,
        "exam_id": exam_id,
        "exam_name": exam_name,
        "profile_name": profile_name
    }
    
    try:
        tasks = []
        if os.path.exists(sync_file):
            with open(sync_file, "r") as f:
                tasks = json.load(f)
        tasks.append(task_data)
        with open(sync_file, "w") as f:
            json.dump(tasks, f)
        print("✅ Sync task queued for v2 analytics database.")
    except Exception as e:
        print(f"⚠️ Failed to queue sync task: {e}")
    # -----------------------------------------------

    return True

if __name__ == "__main__":
    # Internal Test execution 
    pass
