import urllib.request as urllib_req
import re
import json
import os
import smtplib
import time
import hashlib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# auto_pdf_mailer import is now deferred to main() to allow fast-boot detection without dependencies.

# Configuration
AJAX_URL = "https://ducmc.du.ac.bd/ajax/get_program_by_exam.php"
PROGRAMS = {
    "12": "B.Sc. in Civil Engineering",
    "13": "B.Sc. in Electrical and Electronic Engineering",
    "14": "B.Sc. in Computer Science and Engineering"
}

# Paths (Relative to repo root when run by GitHub Action)
MONITOR_DIR = "exam_monitor"
KNOWN_EXAMS_FILE = os.path.join(MONITOR_DIR, "known_exams.json")

def extract_options_from_html(html):
    pattern = r'<option[^>]+value\s*=\s*["\']?([^"\'>\s]*)["\']?[^>]*>(.*?)</option>'
    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
    results = {}
    for val, text in matches:
        clean_text = re.sub(r'<[^>]*>', '', text).strip()
        if val and val != "0":
            results[val] = clean_text
    return results

def fetch_current_exams(pro_id):
    url = f"{AJAX_URL}?program_id={pro_id}&pedata=99"
    try:
        # Standard urllib to avoid external dependencies in GitHub Runner
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib_req.Request(url, headers=headers)
        with urllib_req.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', 'ignore')
            return extract_options_from_html(html)
    except Exception as e:
        print(f"Error fetching for program {pro_id}: {e}")
        return {}

def send_email(dept_name, exams):
    smtp_user = os.getenv("EMAIL_USER")
    smtp_pass = os.getenv("EMAIL_PASS")
    receiver = os.getenv("RECEIVER_EMAIL")

    if not all([smtp_user, smtp_pass, receiver]):
        print(f"Skipping email for {dept_name}: Missing SMTP credentials.")
        return

    subject = f"🔔 New Exam: {dept_name}"
    
    # Generate a unique notification ID for anti-spam
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content_hash = hashlib.md5(f"{dept_name}{list(exams.keys())}{timestamp}".encode()).hexdigest()[:8]
    
    body = f"Respected Administrator,\n\n"
    body += f"This is an official notification that new academic results have been published from the central university portal for the Department of {dept_name}.\n\n"
    body += f"Published Examination(s):\n"
    for ex_id, ex_name in exams.items():
        body += f"• {ex_name}\n"
    
    body += f"\nFor immediate access to the full result sheets, please log in to the Result Finder Dashboard or await the automated PDF delivery dispatch.\n\n"
    body += f"Best Regards,\nResult Finder Monitoring Engine"
    
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = receiver
    msg['Subject'] = subject
    
    # Priority headers to trigger phone notifications
    msg['X-Priority'] = '1 (Highest)'
    msg['X-MSMail-Priority'] = 'High'
    msg['Importance'] = 'High'
    
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Use SSL for Gmail
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        print(f"Notification email sent to {receiver} for {dept_name}")
    except Exception as e:
        print(f"Failed to send email for {dept_name}: {e}")

def main(check_only=False):
    if not os.path.exists(KNOWN_EXAMS_FILE):
        print("State file not found. Creating a new one.")
        known_state = {pid: [] for pid in PROGRAMS}
    else:
        with open(KNOWN_EXAMS_FILE, "r") as f:
            known_state = json.load(f)

    any_new = False
    for pid, dept_name in PROGRAMS.items():
        try:
            print(f"Checking {dept_name}...")
            current_exams = fetch_current_exams(pid)
            
            known_ids = set(known_state.get(pid, []))
            new_found = {eid: name for eid, name in current_exams.items() if eid not in known_ids}
            
            if new_found:
                # 1. Main Exam Filtering
                main_exams = {}
                for eid, name in new_found.items():
                    name_lower = name.lower()
                    exclusions = ["retake", "improvement", "special", "clearance", "backlog", "junior", "short", "carry"]
                    if any(ext in name_lower for ext in exclusions):
                        continue
                    main_exams[eid] = name
                        
                if main_exams:
                    any_new = True
                    print(f"  -> Found {len(main_exams)} new main exams!")
                    
                    if not check_only:
                        # 2. Lazy Import of heavy modules
                        import sys
                        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        if root_dir not in sys.path: sys.path.append(root_dir)
                        import auto_pdf_mailer
                        
                        # 3. Text Notification (Admin)
                        send_email(dept_name, main_exams)
                        
                        # 4. PDF Batch Automation (Admin + Dept Heads)
                        for eid, name in main_exams.items():
                            print(f"    [PDF Pipeline] Triggering for: {name}")
                            try:
                                auto_pdf_mailer.process_and_mail(pid, dept_name, eid, name)
                            except Exception as e:
                                print(f"    [!] PDF Pipeline Error for {name}: {e}")
                
                if not check_only:
                    # Update state for this department immediately
                    known_state[pid] = list(current_exams.keys())
                    # Atomic save
                    with open(KNOWN_EXAMS_FILE, "w") as f:
                        json.dump(known_state, f, indent=4)
                    print(f"  -> State updated for {dept_name}.")
                    time.sleep(5)
        except Exception as e:
            print(f"  [!] Fatal error scanning {dept_name}: {e}")

    if any_new:
        print("Monitor run completed with updates.")
        # Signal to GitHub Actions that we need to upscale to the heavy PDF job
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
                f.write("new_exams=true\n")
    else:
        print("No new exams detected.")
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
                f.write("new_exams=false\n")

if __name__ == "__main__":
    import sys
    check_only = "--check-only" in sys.argv
    main(check_only=check_only)
