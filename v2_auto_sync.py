import os
import json
import cli_scraper as cs
import database as db

SYNC_FILE = "/tmp/v2_sync_tasks.json"


def detect_and_add_readds(profile_name, pro_id, exam_id, exam_name, existing_results):
    """
    After scanning the target batch, checks ALL senior batch profiles of the
    same department.  Any student found in a senior batch whose registration
    number is NOT already in the target profile AND who returns a valid result
    for this exam is treated as a readmitted (readd) student.

    Actions:
      1. Adds the readd student to the target profile's student roster.
      2. Saves the readd student's exam results to the analytics database.
      3. Returns a summary list for logging / notification.
    """
    # Build set of regs already covered (profile roster + current results)
    existing_regs = db.get_profile_student_regs(profile_name)
    for res in existing_results:
        reg = int(res.get('Registration No', res.get('Reg', 0)))
        existing_regs.add(reg)

    # Find all senior batch profiles for same department
    senior_profiles = db.get_senior_batch_profiles(profile_name)
    if not senior_profiles:
        print(f"  [Readd] No senior batch profiles found for '{profile_name}'.")
        return []

    print(f"  [Readd] Scanning {len(senior_profiles)} senior profile(s): "
          f"{', '.join(sorted(senior_profiles.keys()))}")

    # Collect senior students not already in the target profile
    scan_tasks = []
    reg_to_source = {}
    for sp_name, sp_data in senior_profiles.items():
        for r in sp_data.get('regs', []):
            if isinstance(r, list):
                reg = int(r[0])
                sid = str(r[1])
            else:
                reg = int(r)
                sid = str(sp_data.get('sess_id', 'AUTO'))
            if reg not in existing_regs:
                scan_tasks.append((reg, sid, str(exam_id)))
                reg_to_source[reg] = sp_name
                existing_regs.add(reg)  # prevent cross-profile duplicates

    if not scan_tasks:
        print("  [Readd] All senior students already accounted for.")
        return []

    print(f"  [Readd] Probing {len(scan_tasks)} senior students against exam {exam_id}...")

    readd_results = cs.run_batch_scan_engine(
        tasks=scan_tasks,
        pro_id=pro_id,
        exam_id=exam_id,
        target_college="all",
        num_threads=10
    )

    # Filter out "ghosts" (Improvement/Retake students).
    # For Civil (pro_id 12), a real re-add MUST have an SGPA. 
    # For CSE (pro_id 14), the portal is broken, so we are more lenient.
    filtered_readds = []
    for r in readd_results:
        has_subjects = r.get('Subjects') and len(r['Subjects']) > 0
        has_sgpa = str(r.get('SGPA', '-')) != '-'
        
        # Condition: If it's not CSE, we require SGPA to avoid 'Improvement' ghosts
        if str(pro_id) != '14':
            if has_subjects and has_sgpa:
                filtered_readds.append(r)
        else:
            # For CSE, we trust any student with subjects (fallback calc will handle the rest)
            if has_subjects:
                filtered_readds.append(r)
    
    readd_results = filtered_readds

    if not readd_results:
        print("  [Readd] No readd students with valid results detected.")
        return []

    # --- Persist readd students ---
    readd_info = []
    for res in readd_results:
        reg = int(res.get('Registration No', res.get('Reg', 0)))
        name = str(res.get('Name', res.get('Student Name', 'Unknown')))
        sess_id = str(res.get('_sess_id', 'AUTO'))
        source = reg_to_source.get(reg, 'unknown')

        # 1. Add student to target profile roster
        db.upsert_student(profile_name, reg, name, sess_id)

        readd_info.append({
            'reg_no': reg,
            'name': name,
            'sess_id': sess_id,
            'source_profile': source,
        })
        print(f"    [READD] {name} ({reg}) <- from '{source}'")

    # 2. Save all readd exam results to analytics database
    db.save_exam_analytics_only(profile_name, exam_id, exam_name, readd_results)
    print(f"  [Readd] Saved {len(readd_results)} readd result(s) to analytics.")

    return readd_info


def main():
    if not os.path.exists(SYNC_FILE):
        print(f"No sync file found at {SYNC_FILE}")
        return

    try:
        with open(SYNC_FILE, "r") as f:
            tasks_list = json.load(f)
    except Exception as e:
        print(f"Failed to load {SYNC_FILE}: {e}")
        return

    if not tasks_list:
        print("No tasks in sync file.")
        return

    print(f"Found {len(tasks_list)} sync task(s). Starting sync to database...")

    profiles = db.get_profiles()
    
    for task in tasks_list:
        pro_id = task.get("pro_id")
        exam_id = task.get("exam_id")
        exam_name = task.get("exam_name")
        profile_name = task.get("profile_name")
        
        print(f"\n--- Syncing {exam_name} for Profile: {profile_name} ---")
        
        if profile_name not in profiles:
            print(f"Error: Profile '{profile_name}' not found in database. Skipping.")
            continue
            
        p_data = profiles[profile_name]
        regs_raw = p_data.get("regs", [])
        if not regs_raw:
            print(f"Error: Profile '{profile_name}' has no registered students. Skipping.")
            continue
            
        sess_id = p_data.get("sess_id")
        scan_tasks = []
        for item in regs_raw:
            if isinstance(item, list):
                scan_tasks.append((int(item[0]), str(item[1]), str(exam_id)))
            else:
                scan_tasks.append((int(item), str(sess_id), str(exam_id)))
                
        print(f"Fetching results for {len(scan_tasks)} students...")
        
        results = cs.run_batch_scan_engine(
            tasks=scan_tasks,
            pro_id=pro_id,
            exam_id=exam_id,
            target_college="all",
            num_threads=10
        )
        
        if not results:
            print(f"No valid results downloaded for {exam_name}.")
            continue
            
        print(f"Downloaded {len(results)} records. Saving to analytics database...")
        db.save_exam_analytics_only(profile_name, exam_id, exam_name, results)
        print("Save complete.")

        # --- Readd Detection Phase ---
        readd_info = detect_and_add_readds(
            profile_name, pro_id, exam_id, exam_name, results
        )
        if readd_info:
            print(f"\n  [Readd Summary] for {profile_name}:")
            for ri in readd_info:
                print(f"     + {ri['name']} ({ri['reg_no']}) <- {ri['source_profile']}")
            
            # Save to notifications JSON for the analytics dashboard
            notify_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "readd_notifications.json")
            try:
                if os.path.exists(notify_file):
                    with open(notify_file, "r") as nf:
                        notif_data = json.load(nf)
                else:
                    notif_data = {}
                
                key = f"{profile_name}_{exam_id}"
                if key not in notif_data:
                    notif_data[key] = []
                notif_data[key].extend(readd_info)
                
                with open(notify_file, "w") as nf:
                    json.dump(notif_data, nf, indent=4)
                print(f"  [Readd] Saved notification data for dashboard.")
            except Exception as e:
                print(f"  [Readd] Failed to save notification: {e}")

    # Optional cleanup (the workflow may also clean this up)
    try:
        os.remove(SYNC_FILE)
        print("Removed temporary sync tasks file.")
    except Exception as e:
        print(f"Failed to clean up sync file: {e}")

if __name__ == "__main__":
    main()
