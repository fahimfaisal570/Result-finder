import sys
sys.path.append('.')
import cli_scraper as scraper
import threading
import queue
import re
import json
import time

PRO_ID = '14'
EXAM_ID = '1769'
SESSIONS = ['21', '20']

print("Starting scan for all colleges in exam 1769 for sessions 21 and 20...")
results = []
results_lock = threading.Lock()

task_queue = queue.Queue()
total_tasks = 0
for sess in SESSIONS:
    # 1 to 3500 should be enough for CSE registration numbers under DU
    for reg in range(1, 3501):
        task_queue.put((reg, sess))
        total_tasks += 1

completed = 0
print(f"Total tasks: {total_tasks}")

def worker():
    global completed
    while not task_queue.empty():
        try:
            reg, sess = task_queue.get(timeout=1)
        except:
            break
        
        # We increase the request retry or timeout safely in cli_scraper if needed
        data = {'pro_id': PRO_ID, 'sess_id': sess, 'exam_id': EXAM_ID, 'gdata': '99', 'reg_no': str(reg)}
        html = scraper.make_request(scraper.AJAX_URL, data=data)
        
        if html and "Student's Name" in html and "no record found" not in html.lower() and "challenge" not in html.lower():
            college = "Unknown"
            col_match = re.search(r'<th>College Name</th>\s*<td[^>]*>(.*?)</td>', html, re.IGNORECASE | re.DOTALL)
            if col_match:
                college = col_match.group(1).strip()
            else:
                col_fb = re.search(r'(?:College|Institution)\s*(?:Name)?\s*[:\-]?\s*<[^>]+>\s*([^<]+)', html, re.IGNORECASE)
                if col_fb: college = col_fb.group(1).strip()
                
            info, found = scraper.fetch_student_result(reg, PRO_ID, sess, EXAM_ID, target_college="all")
            if found and info:
                info['College'] = college
                with results_lock:
                    results.append(info)
                    print(f"FOUND: {info['Registration No']} - {info['Name']} - {college}")
                    
        with results_lock:
            completed += 1
            if completed % 100 == 0:
                print(f"Progress: {completed}/{total_tasks}")
                
        task_queue.task_done()

threads = []
# 200 threads to smash through 7000 requests in ~1 minute
for _ in range(200):
    t = threading.Thread(target=worker)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

with open('found_results.json', 'w') as f:
    json.dump(results, f, indent=4)

print(f"Total found: {len(results)}")
