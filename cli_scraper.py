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

from __future__ import print_function
import os
import sys
import time
import datetime
def get_bd_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)
import re
import ssl
import subprocess
import collections
import random

# --- Python 2/3 Compatibility Shims ---
if sys.version_info[0] < 3:
    import urllib2 as urllib_req
    import urllib as urllib_parse
    import Queue as queue
    input_func = raw_input
else:
    import urllib.request as urllib_req
    import urllib.parse as urllib_parse
    import queue
    input_func = input
import json
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx, add_report_ctx
except ImportError:
    get_script_run_ctx = add_report_ctx = lambda *args, **kwargs: None

import threading


from scraper_core.network import *
from scraper_core.profiles import *
from scraper_core.parser import *
from scraper_core.reports import *

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
                                final_name = name + "_imported_" + get_bd_time().strftime("%H%M%S")
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
                                with stealth_lock:
                                    if time.time() < global_backoff_until:
                                        time.sleep(random.uniform(3.0, 7.0))
                                
                                sessions_to_try = [sess]
                                if sess == "AUTO":
                                    sessions_to_try = []
                                    with stealth_lock:
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
                                            with stealth_lock:
                                                global_backoff_until = time.time() + 15.0
                                            time.sleep(random.uniform(10.0, 15.0))
                                            continue
                                            
                                        if res and isinstance(res, dict):
                                            found_res = [int(reg), res.get('_sess_id', s), res.get('Name', old_name)]
                                            # Update Session Pin
                                            if sess == "AUTO":
                                                with stealth_lock:
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
                        ts = get_bd_time().strftime("%Y%m%d_%H%M%S")
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
            # NARROWING THE SCOPE: Strictly filter exams by year to increase speed and prevent false positives
            # 1. Determine the earliest possible year for this student
            reg_year_suffix = str(reg_no)[0:2] # Heuristic: First two digits of older reg numbers
            # Safer: Use the session year if provided
            start_search_year = 0
            if sess_id and sess_id != "AUTO":
                # Matches "2022" or similar from session name
                sess_name = sessions.get(sess_id, "")
                y_match = re.search(r"20(\d{2})", sess_name)
                if y_match: start_search_year = int("20" + y_match.group(1))
            
            # 2. Build filtered exam list
            filtered_eids = []
            for eid, ename in exams_cache.items():
                _, _, ey = parse_exam_info(ename)
                if ey and start_search_year:
                    # Allow a 1-year buffer for early publications or overlaps
                    if ey < (start_search_year - 1):
                        continue
                filtered_eids.append(eid)
                
            print("\n🔍 Deep Probing {} relevant examinations...".format(len(filtered_eids)))
            
            q = queue.Queue()
            for eid in filtered_eids: q.put(eid)
            h_lock = threading.Lock()
            
            def history_worker():
                while True:
                    try: eid = q.get_nowait()
                    except queue.Empty: break
                    
                    # SAFETY JITTER: Maintain human-like pace
                    time.sleep(random.uniform(0.15, 0.4))
                    
                    # IDENTITY GUARD: Use PINNED session for 100% accuracy, fall back only if AUTO
                    s_to_try = [sess_id] if sess_id != "AUTO" else sorted(list(sessions.keys()), reverse=True)
                    
                    for tsid in s_to_try:
                        time.sleep(random.uniform(0.05, 0.15))
                        res, _ = fetch_student_result(reg_no, pro_id, tsid, eid)
                        
                        # Verify Result - Must have GPA or Subjects to be valid
                        if res and isinstance(res, dict) and (res.get('GPA') != '-' or res.get('Subjects')):
                            # OPTIONAL: Name check if session exists to prevent ID collisions
                            found_name = res.get('Name', '').lower()
                            if st_name and st_name != "Student" and st_name.lower() not in found_name and found_name not in st_name.lower():
                                # Collision detected (ID matches but Name differs hugely)
                                continue
                                
                            with h_lock:
                                res['_exam_name'] = exams_cache[eid]
                                history.append(res)
                            break
                    print(".", end="", flush=True)
                    sys.stdout.flush()
            
            threads = []
            # Optimized Thread Count for Stability
            thread_count = min(12, len(filtered_eids))
            for _ in range(thread_count):
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
    timestamp = get_bd_time().strftime("%Y%m%d_%H%M%S")
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
