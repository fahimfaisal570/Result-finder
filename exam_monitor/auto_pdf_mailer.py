import os
import sys
import json
import smtplib
import re
import pdfkit
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

def identify_batch_for_exam(pro_id, exam_name):
    """Dynamically finds the appropriate saved profile for an exam."""
    y, sem, ey = cs.parse_exam_info(exam_name)
    if not y or not ey:
        print(f"Could not parse year/exam_year from {exam_name}")
        return None, None
        
    session_start_year = ey - y + 1
    # Convert to 2-digit format used in sess_id (e.g., 2021 -> 21)
    sess_id_target = str(session_start_year)[-2:]
    
    profiles_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saved_profiles.json")
    if not os.path.exists(profiles_path):
        print("saved_profiles.json not found")
        return None, None
        
    try:
        with open(profiles_path, "r") as f:
            profiles = json.load(f)
            
        for p_name, p_data in profiles.items():
            if str(p_data.get("pro_id")) == str(pro_id) and str(p_data.get("sess_id")) == sess_id_target:
                return p_name, p_data
    except Exception as e:
        print(f"Error loading profiles: {e}")
        
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

def generate_thesis_pdf_html(results, exam_name, dept_name, profile_name):
    # Sort results
    def get_reg_sort_key(res):
        try: return (0, int(res['Registration No']))
        except Exception: return (1, str(res['Registration No']))
    results.sort(key=get_reg_sort_key)

    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>Official Academic Result</title>
    <style>
        body {{
            font-family: "Times New Roman", Times, serif;
            margin: 0;
            padding: 20px;
            color: #000;
            background-color: #fff;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #000;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }}
        .header h1 {{ margin: 0; font-size: 26px; text-transform: uppercase; letter-spacing: 1px; }}
        .header h2 {{ margin: 8px 0; font-size: 20px; font-weight: normal; }}
        .header h3 {{ margin: 5px 0; font-size: 16px; color: #222; font-style: italic; }}
        .header h4 {{ margin: 5px 0; font-size: 14px; font-weight: bold; margin-top: 15px; }}
        
        .student-block {{
            page-break-inside: avoid;
            margin-bottom: 30px;
            border: 1px solid #000;
            padding: 15px;
        }}
        .student-header {{
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 15px;
            padding-bottom: 5px;
            border-bottom: 1px solid #000;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            border: 1px solid #000;
            padding: 8px;
            text-align: left;
        }}
        th {{ background-color: #f8f9fa; font-weight: bold; text-align: center; }}
        td.center {{ text-align: center; }}
        .summary {{
            margin-top: 15px;
            font-weight: bold;
            text-align: right;
            font-size: 15px;
        }}
        .footer {{
            text-align: center;
            font-size: 11px;
            color: #555;
            margin-top: 50px;
            border-top: 1px dashed #ccc;
            padding-top: 10px;
        }}
    </style>
    </head>
    <body>
        <div class="header">
            <h1>Faridpur Engineering College</h1>
            <h2>Department of {dept_name}</h2>
            <h3>{exam_name}</h3>
            <h4>Official Result Batch Profile: {profile_name}</h4>
        </div>
    """

    for r in results:
        reg = r.get('Registration No', 'N/A')
        name = r.get('Name') or r.get('Student Name', 'Unknown')
        status = r.get('Overall Result', '-')
        gpa = r.get('GPA', '-')
        cgpa = r.get('CGPA', '-')
        
        html += f"""
        <div class="student-block">
            <div class="student-header">
                Registration No: {reg} &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; Student Name: {name}
            </div>
        """
        
        if r.get('Subjects'):
            html += """
            <table>
                <tr>
                    <th width="15%">Course Code</th>
                    <th width="55%">Course Title</th>
                    <th width="15%">Letter Grade</th>
                    <th width="15%">Grade Point</th>
                </tr>
            """
            for s in r['Subjects']:
                html += f"""
                <tr>
                    <td class="center">{s.get('code','')}</td>
                    <td>{s.get('name','')}</td>
                    <td class="center">{s.get('grade','')}</td>
                    <td class="center">{s.get('gp','')}</td>
                </tr>
                """
            html += "</table>"
            
        html += f"""
            <div class="summary">
                Status: {status} &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; GPA: {gpa} &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; CGPA: {cgpa}
            </div>
        </div>
        """
        
    html += f"""
        <div class="footer">
            Generated Automatically by Result Finder Monitor Engine<br>
            Timestamp: {timestamp}
        </div>
    </body>
    </html>
    """
    return html

def process_and_mail(pro_id, dept_name, exam_id, exam_name):
    print(f"\n--- Initiating Auto-Scan Flow for {exam_name} ---")
    
    profile_name, p_data = identify_batch_for_exam(pro_id, exam_name)
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
    html_report = generate_thesis_pdf_html(results, exam_name, dept_name, profile_name)
    
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
            'no-stop-slow-scripts': None,
            'javascript-delay': 2000
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
