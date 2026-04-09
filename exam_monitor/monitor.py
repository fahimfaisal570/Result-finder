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
try:
    import auto_pdf_mailer
except ImportError:
    # Handle if run from outside directory
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import auto_pdf_mailer

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
    
    body = f"New exam(s) detected for {dept_name}:\n\n"
    for ex_id, ex_name in exams.items():
        body += f"• {ex_name}\n  (Internal ID: {ex_id})\n"
    
    body += f"\nCheck official site: https://ducmc.du.ac.bd/result.php\n"
    body += f"Quick Finder: https://fec-result-finder.streamlit.app/\n"
    body += f"Analytics Dashboard: https://fec-result-analytics.streamlit.app/\n\n"
    body += "---\n"
    body += f"Sent via Result Finder Monitor\n"
    body += f"Notification ID: {content_hash} | {timestamp}"

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

def main():
    if not os.path.exists(KNOWN_EXAMS_FILE):
        print("State file not found. Creating a new one.")
        known_state = {pid: [] for pid in PROGRAMS}
    else:
        with open(KNOWN_EXAMS_FILE, "r") as f:
            known_state = json.load(f)

    any_new = False
    for pid, dept_name in PROGRAMS.items():
        print(f"Checking {dept_name}...")
        current_exams = fetch_current_exams(pid)
        
        known_ids = set(known_state.get(pid, []))
        new_found = {eid: name for eid, name in current_exams.items() if eid not in known_ids}
        
        if new_found:
            print(f"  -> Found {len(new_found)} new exams!")
            
            # 1. Main Exam Filtering
            main_exams = {}
            for eid, name in new_found.items():
                name_lower = name.lower()
                exclusions = ["retake", "improvement", "special", "clearance", "backlog", "junior", "short", "carry"]
                if any(ext in name_lower for ext in exclusions):
                    print(f"    [SKIP] Found non-main exam: {name}")
                else:
                    main_exams[eid] = name
                    
            if main_exams:
                # 2. Text Notification (Admin)
                send_email(dept_name, main_exams)
                
                # 3. PDF Batch Automation (Admin + Dept Heads)
                for eid, name in main_exams.items():
                    print(f"    [PDF Pipeline] Triggering for: {name}")
                    auto_pdf_mailer.process_and_mail(pid, dept_name, eid, name)
            
            any_new = True
            # Update state for this department immediately
            known_state[pid] = list(current_exams.keys())
            # Anti-spam delay
            print("  -> Sleeping 5s for anti-spam...")
            time.sleep(5)

    if any_new:
        # Update state file
        with open(KNOWN_EXAMS_FILE, "w") as f:
            json.dump(known_state, f, indent=4)
        print("State updated.")
    else:
        print("No new exams detected.")

if __name__ == "__main__":
    main()
