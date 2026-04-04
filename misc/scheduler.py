"""
Background Auto-Scheduler Daemon
Runs periodically to fetch updated exam results for all tracked profiles.
Idempotent and safe to run alongside Streamlit.
"""
import time
import logging
import database as db
import cli_scraper as cs
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def run_scheduler_cycle():
    logger.info("Starting scheduler cycle...")
    profiles = db.get_profiles()
    
    if not profiles:
        logger.info("No profiles found in database. Nothing to scan.")
        return

    for p_name, p_data in profiles.items():
        if config.SCAN_ONLY_PROFILES and p_name not in config.SCAN_ONLY_PROFILES:
            logger.debug(f"Skipping profile {p_name} (not in SCAN_ONLY_PROFILES)")
            continue

        pro_id = p_data.get("pro_id")
        if not pro_id:
            logger.warning(f"Profile {p_name} has no pro_id. Skipping.")
            continue

        logger.info(f"Checking profile: {p_name} (pro_id: {pro_id})")
        
        try:
            # Fetch available exams from upstream
            exams = cs.fetch_exams(pro_id)
        except Exception as e:
            logger.error(f"Failed to fetch exams for program {pro_id}: {e}")
            continue

        for exam_id, exam_name in exams.items():
            if db.should_rescan(p_name, exam_id, config.SCAN_INTERVAL_MINUTES):
                logger.info(f" -> Rescanning {exam_name} ({exam_id})")
                
                # Fetch all reg_nos for this profile
                regs = [r[0] for r in p_data.get("regs", [])]
                if not regs:
                    continue

                try:
                    # Execute batch scan
                    results = cs.run_batch_scan_engine(
                        tasks=regs,
                        pro_id=pro_id,
                        exam_id=exam_id,
                        # Pass defaults for session and callback
                        all_sessions=None,
                        progress_callback=None,
                        num_threads=config.THREADS_PER_SCAN
                    )
                    
                    if results:
                        db.save_exam_analytics_only(p_name, exam_id, exam_name, results)
                        logger.info(f"    Saved {len(results)} results for {p_name} / {exam_name}")
                    else:
                        # Log empty scan to avoid spinning
                        db.update_scan_log(p_name, exam_id, 0)
                        logger.info(f"    No results found. Logged empty scan to prevent immediate retry.")
                except Exception as e:
                    logger.error(f"Scan failed for {exam_name}: {e}")
            else:
                logger.debug(f" -> Skipping {exam_name} (scanned recently)")

def main():
    logger.info(f"Scheduler daemon started. Interval: {config.SCAN_INTERVAL_MINUTES} mins.")
    while True:
        try:
            run_scheduler_cycle()
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user.")
            break
        except Exception as e:
            logger.error(f"Unhandled error in scheduler cycle: {e}")
            
        wait_seconds = max(60, config.SCAN_INTERVAL_MINUTES * 60)
        logger.info(f"Sleeping for {wait_seconds} seconds before next cycle...")
        
        try:
            time.sleep(wait_seconds)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user during sleep.")
            break

if __name__ == "__main__":
    main()
