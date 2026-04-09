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
        std_regs = [str(r) for r in regs_raw if not isinstance(r, list)]
        if std_regs:
            step = max(1, len(std_regs) // 5)
            samples = std_regs[::step][:5]
            
        # Fallback to re-adds if no standard students exist
        if not samples and regs_raw:
            r = regs_raw[0]
            if isinstance(r, list): samples.append(str(r[0]))
            
        for test_reg in samples:
            res_data, success = cs.fetch_student_result(test_reg, pro_id, sess_id, exam_id)
            if success and isinstance(res_data, dict) and 'Total Credit' in res_data:
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
        
    print(f"✅ Downloaded {len(results)} student records. Generating Printable Thesis HTML format...")
    # Inject profile_name into title so it appears nicely in the central PDF rendering engine
    full_title = f"Department: {dept_name} | Exam: {exam_name} | Target Batch: {profile_name}"
    html_report = cs.generate_html_report(results, full_title, pro_id=pro_id, sess_id=sess_id)
    
    import pdfkit  # Defer import for fast-boot optimization
    print("📄 Rendering HTML to PDF Format...")
    try:
        # options to ensure CSS renders correctly and fits the page
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
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
    return True

if __name__ == "__main__":
    # Internal Test execution 
    pass
