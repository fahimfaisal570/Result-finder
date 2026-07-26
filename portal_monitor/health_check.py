import urllib.request
import urllib.error
import json
import os
import smtplib
import time
import contextlib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
CHECK_URL = "https://ducmc.du.ac.bd/"
ALERT_RECIPIENT = os.getenv("RECEIVER_EMAIL", "")
PORTAL_MONITOR_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PORTAL_MONITOR_DIR, "state.json")
BD_TZ = timezone(timedelta(hours=6))

# Custom 5-line parser to load a local .env file for local development/testing
def load_env():
    root_dir = os.path.dirname(PORTAL_MONITOR_DIR)
    env_path = os.path.join(root_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

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
                break
            time.sleep(0.2)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.rmdir(lock_dir)

def check_portal():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(CHECK_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', 'ignore')
                
                # POSITIVE VERIFICATION (WHITE-LISTING CRITERIA)
                # The portal is only healthy/online if it loads with DUCMC details
                # and contains NO CrowdSec blocks or database failures.
                is_valid = ("DUCMC" in html) and ("University of Dhaka" in html)
                is_waf_blocked = "CrowdSec" in html or "Access Forbidden" in html
                
                if is_valid and not is_waf_blocked:
                    return "online", "Response verified successfully."
                elif is_waf_blocked:
                    return "offline", "WAF/CrowdSec Access Block detected."
                else:
                    return "offline", "Failed positive signature verification (unexpected page contents)."
                    
        except urllib.error.HTTPError as e:
            # Handle specific WAF/Proxy/Server errors
            if e.code in [401, 403]:
                # If we get a 403, check if it's the CrowdSec block page
                try:
                    body = e.read().decode('utf-8', 'ignore')
                    if "CrowdSec" in body:
                        return "offline", f"WAF Block (HTTP {e.code}): CrowdSec Access Forbidden."
                except:
                    pass
                return "offline", f"HTTP Error {e.code}: Access Forbidden."
            elif attempt < max_retries - 1:
                time.sleep(5)
                continue
            return "offline", f"HTTP Error {e.code}: {e.reason}."
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return "offline", f"Connection failed: {e}."
            
    return "offline", "Failed after retries."

def send_alert_email(new_status, reason):
    smtp_user = os.getenv("EMAIL_USER")
    smtp_pass = os.getenv("EMAIL_PASS")
    
    if not smtp_user or not smtp_pass or not ALERT_RECIPIENT:
        print("Skipping email: Missing SMTP credentials or ALERT_RECIPIENT (EMAIL_USER/EMAIL_PASS/RECEIVER_EMAIL).")
        return
        
    subject = f"🔔 Portal Alert: DUCMC is {'ONLINE' if new_status == 'online' else 'DOWN'}"
    timestamp = datetime.now(BD_TZ).strftime("%Y-%m-%d %H:%M:%S BST (UTC+6)")
    
    body = f"The Dhaka University Constituent Colleges (DUCMC) portal state has changed.\n\n"
    body += f"Current State: {new_status.upper()}\n"
    body += f"Status Reason: {reason}\n"
    body += f"Detected At  : {timestamp}\n\n"
    body += f"Target URL   : {CHECK_URL}\n\n"
    body += "This is an automated delivery from the isolated portal uptime monitor."
    
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = ALERT_RECIPIENT
    msg['Subject'] = subject
    
    # Priority headers to trigger phone push alerts
    msg['X-Priority'] = '1 (Highest)'
    msg['X-MSMail-Priority'] = 'High'
    msg['Importance'] = 'High'
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        print(f"✅ Alert email dispatched successfully to {ALERT_RECIPIENT}")
    except Exception as e:
        print(f"❌ Failed to dispatch email alert: {e}")

def main():
    load_env()
    
    import sys
    # Support manual force-test arguments
    force_status = None
    if "--force-online" in sys.argv:
        force_status = "online"
    elif "--force-offline" in sys.argv:
        force_status = "offline"
        
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting portal health check...")
    
    if force_status:
        current_status, reason = force_status, f"Manual verification trigger (--force-{force_status})"
    else:
        current_status, reason = check_portal()
        
    print(f"Status check result: {current_status.upper()} ({reason})")
    
    with file_process_lock(STATE_FILE):
        # Load previous status
        prev_status = "online" # default fallback
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    state_data = json.load(f)
                    prev_status = state_data.get("last_status", "online")
            except Exception as e:
                print(f"Failed to load state file: {e}. Re-initializing...")
                
        # Handle state changes or test triggers
        state_changed = (current_status != prev_status)
        is_test_run = "--test-email" in sys.argv
        
        if state_changed or is_test_run:
            print(f"State transition detected: {prev_status.upper()} -> {current_status.upper()} (or --test-email provided). Triggering email...")
            send_alert_email(current_status, reason if not is_test_run else f"{reason} [Test Run]")
        else:
            print(f"No state change detected (still {current_status.upper()}). Silent exit.")
            
        # Update persistent state
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "last_status": current_status,
                    "last_check": datetime.now(BD_TZ).strftime("%Y-%m-%d %H:%M:%S BST")
                }, f, indent=4)
        except Exception as e:
            print(f"Failed to save state file: {e}")

if __name__ == "__main__":
    main()
