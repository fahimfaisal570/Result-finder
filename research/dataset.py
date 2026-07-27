"""
research/dataset.py — Structured Research Dataset Layer & Taxonomy
Generates anonymized, ground-truth labeled research dataset from university result database.
"""

import os
import hashlib
import json
import logging
from enum import Enum
import pandas as pd
import database as db

logger = logging.getLogger(__name__)

SALT_ENV_VAR = "RESEARCH_ANON_SALT"
DEFAULT_SALT = "result_finder_research_salt_2026"

class AcademicState(str, Enum):
    REGULAR = "regular"
    RETAKE_CANDIDATE = "retake_candidate"
    IMPROVEMENT_CANDIDATE = "improvement_candidate"
    READMITTED = "readmitted"
    AT_RISK = "at_risk"
    STABLE = "stable"
    HIGH_PERFORMER = "high_performer"
    DECLINING = "declining"

def anonymize_student_id(reg_no: int | str, salt: str | None = None) -> str:
    """Computes standard one-way SHA-256 anonymized hash for student registration number."""
    if salt is None:
        salt = os.getenv(SALT_ENV_VAR, DEFAULT_SALT)
    payload = f"{salt}:{reg_no}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]

def classify_academic_state(
    cgpa: float,
    prev_cgpa: float | None = None,
    trend_slope: float | None = None,
    is_readd: bool = False,
    has_retakes: bool = False,
    promo_target: float | None = None
) -> str:
    """Strict taxonomy classifier for academic state."""
    if is_readd:
        return AcademicState.READMITTED.value
    if promo_target and cgpa < promo_target:
        return AcademicState.AT_RISK.value
    if cgpa >= 3.75:
        return AcademicState.HIGH_PERFORMER.value
    if trend_slope is not None and trend_slope < -0.15:
        return AcademicState.DECLINING.value
    if has_retakes:
        return AcademicState.RETAKE_CANDIDATE.value
    if prev_cgpa is not None and abs(cgpa - prev_cgpa) <= 0.05:
        return AcademicState.STABLE.value
    return AcademicState.REGULAR.value

def populate_research_dataset(salt: str | None = None) -> int:
    """
    Extracts all records from database.py, derives labels & academic taxonomy,
    and upserts into SQLite research_records table.
    Returns count of records inserted.
    """
    profiles = db.get_profiles()
    if not profiles:
        return 0

    records = []
    
    # Read readd_notifications for ground-truth re-admit labels
    readd_set = set()
    readd_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "readd_notifications.json")
    if os.path.exists(readd_json_path):
        try:
            with open(readd_json_path, 'r') as f:
                rdata = json.load(f)
                for key, val_list in rdata.items():
                    if isinstance(val_list, list):
                        for item in val_list:
                            if isinstance(item, dict) and "reg_no" in item:
                                readd_set.add(int(item["reg_no"]))
        except Exception as e:
            logger.warning("Could not parse readd_notifications.json: %s", e)

    with db.get_connection() as conn:
        # Fetch raw grades joined with student and exam details
        query = """
            SELECT 
                sg.profile_name,
                sg.reg_no,
                sg.sess_id,
                sg.exam_id,
                sg.subject_code,
                sg.credit_hours,
                sg.grade_point,
                er.gpa as semester_gpa,
                er.cgpa as semester_cgpa,
                er.exam_name,
                er.raw_json
            FROM subject_grades sg
            LEFT JOIN exam_results er 
                ON sg.profile_name = er.profile_name 
                AND sg.reg_no = er.reg_no 
                AND sg.exam_id = er.exam_id
                AND sg.sess_id = er.sess_id
        """
        rows = conn.execute(query).fetchall()

        # Track retakes per student+subject
        subject_counts = {}
        for row in rows:
            key = (row[1], str(row[4]).strip().upper())
            subject_counts[key] = subject_counts.get(key, 0) + 1

        for row in rows:
            prof_name, reg_no, sess_id, exam_id, sub_code, credit, gp, sem_gpa, sem_cgpa, exam_name, raw_json = row
            dept = db.get_dept_from_profile(prof_name)
            anon_id = anonymize_student_id(reg_no, salt)
            
            # Infer semester number (1..8) from exam_name
            sem_num = 1
            if exam_name:
                import re
                sem_match = re.search(r"(\d)[a-z]{2}\s*(?:Sem|Semester)", str(exam_name), re.IGNORECASE)
                yr_match = re.search(r"(\d)[a-z]{2}\s*(?:Yr|Year)", str(exam_name), re.IGNORECASE)
                if sem_match and yr_match:
                    sem_num = (int(yr_match.group(1)) - 1) * 2 + int(sem_match.group(1))
                elif sem_match:
                    sem_num = int(sem_match.group(1))

            sub_key = (reg_no, str(sub_code).strip().upper())
            retake_flag = 1 if subject_counts.get(sub_key, 0) > 1 else 0
            improvement_flag = 1 if retake_flag and gp > 0.0 else 0
            readd_flag = 1 if int(reg_no) in readd_set else 0

            cgpa_val = float(sem_cgpa) if sem_cgpa else 0.0
            state = classify_academic_state(
                cgpa=cgpa_val,
                is_readd=bool(readd_flag),
                has_retakes=bool(retake_flag)
            )

            records.append((
                anon_id, dept, str(sess_id), sem_num, str(exam_id),
                str(sub_code).strip().upper(), float(credit or 3.0), float(gp or 0.0),
                retake_flag, improvement_flag, readd_flag, state,
                None, None, None, None, float(sem_gpa or 0.0)
            ))

        # Clear and insert into research_records
        conn.execute("DELETE FROM research_records")
        conn.executemany("""
            INSERT INTO research_records (
                anon_student_id, department, session, semester, exam_id,
                subject_code, credit, grade_point, retake_flag, improvement_flag,
                readd_flag, academic_state, publication_ts, detection_ts,
                sync_ts, prediction_output, actual_outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()

    return len(records)

def get_research_dataframe() -> pd.DataFrame:
    """Returns all records in research_records table as pandas DataFrame."""
    with db.get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM research_records", conn)

def export_research_csv(filepath: str | None = None) -> str:
    """Exports research_records table to CSV."""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "research_dataset.csv")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df = get_research_dataframe()
    df.to_csv(filepath, index=False)
    return filepath
