import os
import json
import tempfile
import cli_scraper as cs
import database as db
SYNC_FILE = os.getenv("SYNC_FILE_PATH", os.path.join(tempfile.gettempdir(), "v2_sync_tasks.json"))

def detect_and_add_readds(profile_name, pro_id, exam_id, exam_name, existing_results):
    """
    After scanning the target batch, checks ALL senior batch profiles of the
    same department.  Any student found in a senior batch whose registration
    number is NOT already in the target profile AND who returns a valid result
    for this exam is treated as a readmitted (readd) student, IF their subjects overlap.

    Actions:
      1. Adds the readd student to the target profile's student roster.
      2. Saves the readd student's exam results to the analytics database.
      3. Returns a summary list for logging / notification.
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
        return []

    # Reference = subject codes taken by >=30% of valid regular students
    min_freq = max(1, valid_student_count * 0.3)
    reference_codes = {code for code, count in subject_freq.items() if count >= min_freq}

    if not reference_codes:
        print("  [Readd] Could not build reference subject set. Skipping.")
        return []

    print(f"  [Readd] Reference fingerprint: {len(reference_codes)} subjects from {valid_student_count} regular students")

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

    # --- Step 4: Subject-overlap ghost filter ---
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

            # Auto-promote provisional profiles (V2 branch)
            try:
                p_meta = db.get_profiles()
                if p_meta.get(profile_name, {}).get('is_provisional'):
                    db.promote_provisional_profile(profile_name)
                    print(f"  [Promotion] '{profile_name}' promoted from provisional to full (V2 branch).")
            except Exception as e:
                print(f"  [Promotion] Warning: {e}")

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
                    print("  [Readd] Saved notification data for dashboard.")
                except Exception as e:
                    print(f"  [Readd] Failed to save notification: {e}")
    finally:
        # Optional cleanup (the workflow may also clean this up)
        try:
            if os.path.exists(SYNC_FILE):
                os.remove(SYNC_FILE)
                print("Removed temporary sync tasks file.")
        except Exception as e:
            print(f"Failed to clean up sync file: {e}")

if __name__ == "__main__":
    main()
