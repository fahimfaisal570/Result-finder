import os
import json
import cli_scraper as cs
import database as db

SYNC_FILE = "/tmp/v2_sync_tasks.json"

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

    # Optional cleanup (the workflow may also clean this up)
    try:
        os.remove(SYNC_FILE)
        print("Removed temporary sync tasks file.")
    except Exception as e:
        print(f"Failed to clean up sync file: {e}")

if __name__ == "__main__":
    main()
