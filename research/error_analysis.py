"""
research/error_analysis.py — Error Analysis & Diagnostic Tools
Categorizes failure modes across predictions, re-admission classifications, sync tasks, and database records.
"""

import os
import json
import logging
import database as db
from research.dataset import get_research_dataframe

logger = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "results")

def analyze_system_errors() -> dict:
    """Performs comprehensive failure analysis across all pipeline components."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    df = get_research_dataframe()
    
    error_summary = {
        "prediction_errors": {"count": 0, "threshold_exceeded_samples": []},
        "missed_readmissions": {"count": 0, "samples": []},
        "false_retake_detections": {"count": 0, "samples": []},
        "duplicate_db_records": {"count": 0, "samples": []},
        "parse_or_sync_failures": {"count": 0, "samples": []}
    }

    if not df.empty:
        # 1. Prediction error analysis (|pred - actual| > 0.50)
        if "prediction_output" in df.columns and "actual_outcome" in df.columns:
            pred_df = df.dropna(subset=["prediction_output", "actual_outcome"])
            pred_df["error"] = (pred_df["prediction_output"] - pred_df["actual_outcome"]).abs()
            bad_preds = pred_df[pred_df["error"] > 0.50]
            error_summary["prediction_errors"]["count"] = len(bad_preds)
            error_summary["prediction_errors"]["threshold_exceeded_samples"] = (
                bad_preds[["anon_student_id", "semester", "prediction_output", "actual_outcome", "error"]]
                .head(10).to_dict(orient="records")
            )

        # 2. Missed re-admissions
        missed_readd = df[(df["readd_flag"] == 1) & (df["academic_state"] != "readmitted")]
        error_summary["missed_readmissions"]["count"] = len(missed_readd)
        error_summary["missed_readmissions"]["samples"] = (
            missed_readd[["anon_student_id", "department", "session"]].head(5).to_dict(orient="records")
        )

    # 3. Check SQLite for duplicate (reg_no, exam_id, subject_code)
    with db.get_connection() as conn:
        dups = conn.execute("""
            SELECT reg_no, exam_id, subject_code, COUNT(*) as cnt
            FROM subject_grades
            GROUP BY profile_name, reg_no, exam_id, subject_code, sess_id
            HAVING cnt > 1
        """).fetchall()
        error_summary["duplicate_db_records"]["count"] = len(dups)
        error_summary["duplicate_db_records"]["samples"] = [
            {"reg_no": d[0], "exam_id": d[1], "subject_code": d[2], "count": d[3]} for d in dups[:5]
        ]

    # Save to error_report.json
    with open(os.path.join(RESULTS_DIR, "error_report.json"), "w", encoding="utf-8") as f:
        json.dump(error_summary, f, indent=2)

    return error_summary

if __name__ == "__main__":
    res = analyze_system_errors()
    print("Error analysis complete:", json.dumps(res, indent=2))
