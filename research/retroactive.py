"""
research/retroactive.py — Retroactive Operational Metrics Parser
Computes main-branch operational metrics (detection latency, sync delay) from existing database and JSON artifacts
without modifying or disturbing the autonomous main branch.
"""

import os
import json
import time
import logging
import database as db
from research.metrics import log_metric

logger = logging.getLogger(__name__)

def compute_sync_latency_metrics() -> list[dict]:
    """
    Parses v2_sync_tasks.json and exam_results timestamps to measure sync latency.
    """
    results = []
    sync_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "v2_sync_tasks.json")
    if not os.path.exists(sync_file):
        return results

    try:
        with open(sync_file, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
            for t in tasks:
                t_time = t.get("timestamp")
                exam_id = str(t.get("exam_id"))
                if t_time and exam_id:
                    # Query earliest DB insert for this exam_id
                    with db.get_connection() as conn:
                        row = conn.execute(
                            "SELECT MIN(id) FROM exam_results WHERE exam_id = ?", (exam_id,)
                        ).fetchone()
                        if row and row[0]:
                            sync_latency = max(0.0, time.time() - float(t_time))
                            log_metric("sync_latency", sync_latency, {"exam_id": exam_id, "profile": t.get("profile_name")})
                            results.append({"exam_id": exam_id, "sync_latency": sync_latency})
    except Exception as e:
        logger.warning("Failed parsing sync latency retroactively: %s", e)

    return results

def compute_publication_to_detection_metrics() -> list[dict]:
    """
    Extracts raw publication date from raw_json in exam_results and compares with database entry time.
    """
    metrics = []
    with db.get_connection() as conn:
        rows = conn.execute("SELECT exam_id, exam_name, raw_json FROM exam_results WHERE raw_json IS NOT NULL").fetchall()
        for exam_id, exam_name, raw_json in rows:
            if not raw_json:
                continue
            try:
                data = json.loads(raw_json)
                pub_date_str = data.get("Publication Date") or data.get("pub_date")
                if pub_date_str:
                    log_metric("exam_publication_record", 1.0, {"exam_id": exam_id, "exam_name": exam_name, "pub_date": pub_date_str})
                    metrics.append({"exam_id": exam_id, "exam_name": exam_name, "pub_date": pub_date_str})
            except Exception:
                pass
    return metrics
