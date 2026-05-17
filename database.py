"""
database.py — Result Finder SQLite Layer
ACID-safe, idempotent, retake-aware.
All writes use INSERT OR REPLACE or explicit DELETE+INSERT to prevent duplicates.
"""
import sqlite3
import json
import os
import time
import logging
import re
import streamlit as st

logger = logging.getLogger(__name__)

# --- Database Configuration ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_finder.db")
CREDIT_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credit_mapping.json")



# Load Credit Mapping if exists
_credit_map = {}
if os.path.exists(CREDIT_MAP_PATH):
    try:
        with open(CREDIT_MAP_PATH, 'r') as f:
            _credit_map = json.load(f)
    except:
        pass

def get_dept_from_profile(profile_name: str) -> str:
    """Map profile names like 'cse 09' or 'eee 09' to PDF department keys."""
    p = str(profile_name).lower()
    if 'cse' in p: return "CSE"
    if 'eee' in p: return "EEE"
    if 'civil' in p: return "Civil"
    return "CSE" # Default fallback

def get_subject_credits(subject_code: str, profile_name: str, exam_name: str = None) -> float:
    """Lookup credits from the nested PDF mapping with semester-aware override support."""
    code = str(subject_code).strip().upper().replace(' ', '-')
    dept = get_dept_from_profile(profile_name)
    
    # 1. Semester-aware hard overrides for multi-part subjects (like Thesis)
    if code == "CE-700" and exam_name:
        if "2nd Semester" in exam_name:
            return 3.0
        if "1st Semester" in exam_name:
            return 1.5

    # 2. Check for specific Exam Overrides first
    if exam_name:
        overrides = _credit_map.get("Overrides", {})
        # Try to find a match in the exam name
        for exam_key, subjects in overrides.items():
            if exam_key in exam_name:
                if code in subjects:
                    return subjects[code]
    
    # 3. Check the standard department bucket
    dept_map = _credit_map.get(dept, {})
    if code in dept_map:
        return dept_map[code]
    
    # 5. Global Fallback Policy
    # We NO LONGER default to 3.0. Returning None allows the caller
    # to detect missing mappings and fall back to portal data if needed.
    return None
def get_connection():
    """
    Returns a local SQLite database connection.
    (Turso Cloud Mode is currently disabled).
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Create base schema (v1 tables) — safe to call on every startup."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                name     TEXT PRIMARY KEY,
                pro_id   TEXT NOT NULL,
                sess_id  TEXT,
                timestamp REAL
            );

            CREATE TABLE IF NOT EXISTS students (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_name TEXT NOT NULL,
                reg_no       INTEGER NOT NULL,
                name         TEXT,
                sess_id      TEXT,
                FOREIGN KEY(profile_name) REFERENCES profiles(name) ON DELETE CASCADE,
                UNIQUE(profile_name, reg_no)
            );

            CREATE TABLE IF NOT EXISTS exam_results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_name  TEXT NOT NULL,
                reg_no        INTEGER NOT NULL,
                exam_id       TEXT NOT NULL,
                exam_name     TEXT,
                result_status TEXT,
                sgpa          REAL DEFAULT 0.0,
                cgpa          REAL DEFAULT 0.0,
                raw_json      TEXT,
                FOREIGN KEY(profile_name) REFERENCES profiles(name) ON DELETE CASCADE,
                UNIQUE(profile_name, reg_no, exam_id)
            );

            CREATE TABLE IF NOT EXISTS meta_cache (
                key       TEXT PRIMARY KEY,
                value     TEXT NOT NULL,
                cached_at REAL NOT NULL
            );
        """)
        conn.commit()


def migrate_schema_v2():
    """
    Idempotent migration to v2:
    - Adds subject_grades table (per-subject, per-exam, per-student)
    - Adds scan_log table (tracks when each profile+exam was last auto-scanned)
    - Drops duplicate rows from legacy data before the UNIQUE constraint was added
    """
    with get_connection() as conn:
        cur = conn.cursor()

        # --- subject_grades ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subject_grades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_name TEXT NOT NULL,
                reg_no       INTEGER NOT NULL,
                exam_id      TEXT NOT NULL,
                subject_code TEXT NOT NULL,
                subject_name TEXT,
                grade_point  REAL DEFAULT 0.0,
                credit_hours REAL DEFAULT 3.0,
                FOREIGN KEY(profile_name) REFERENCES profiles(name) ON DELETE CASCADE,
                UNIQUE(profile_name, reg_no, subject_code, exam_id)
            )
        """)

        # --- scan_log ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scan_log (
                profile_name  TEXT NOT NULL,
                exam_id       TEXT NOT NULL,
                scanned_at    REAL NOT NULL,
                student_count INTEGER DEFAULT 0,
                PRIMARY KEY(profile_name, exam_id)
            )
        """)

        # --- De-duplicate legacy exam_results rows (keep lowest id per unique key) ---
        cur.execute("""
            DELETE FROM exam_results
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM exam_results
                GROUP BY profile_name, reg_no, sess_id, exam_id
            )
        """)

        # --- De-duplicate legacy students rows ---
        cur.execute("""
            DELETE FROM students
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM students
                GROUP BY profile_name, reg_no, sess_id
            )
        """)

        conn.commit()
        logger.info("Schema v2 migration complete.")


def migrate_schema_v3():
    """
    Idempotent migration to v3:
    - Adds portal_sgpa to exam_results for shadow auditing.
    - Adds portal_cgpa to exam_results for shadow auditing.
    """
    with get_connection() as conn:
        # PRAGMA table_info returns (id, name, type, notnull, dflt_value, pk)
        cur = conn.execute("PRAGMA table_info(exam_results)")
        cols = [row[1] for row in cur.fetchall()]
        
        if 'portal_sgpa' not in cols:
            conn.execute("ALTER TABLE exam_results ADD COLUMN portal_sgpa REAL")
            logger.info("Added portal_sgpa column to exam_results.")
        
        if 'portal_cgpa' not in cols:
            conn.execute("ALTER TABLE exam_results ADD COLUMN portal_cgpa REAL")
            logger.info("Added portal_cgpa column to exam_results.")
            
        conn.commit()


def migrate_schema_v4():
    """
    Idempotent migration to v4:
    - Adds sess_id to exam_results and subject_grades tables.
    - Recreates students, exam_results, and subject_grades with updated
      UNIQUE constraints that include sess_id, allowing two students
      with the same reg_no but different sessions in the same profile.
    """
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")

        # --- Add sess_id column to exam_results if missing ---
        er_cols = [r[1] for r in conn.execute("PRAGMA table_info(exam_results)").fetchall()]
        if 'sess_id' not in er_cols:
            conn.execute("ALTER TABLE exam_results ADD COLUMN sess_id TEXT NOT NULL DEFAULT 'AUTO'")
            # Backfill sess_id from students table
            conn.execute("""
                UPDATE exam_results
                SET sess_id = COALESCE(
                    (SELECT s.sess_id FROM students s
                     WHERE s.profile_name = exam_results.profile_name
                       AND s.reg_no = exam_results.reg_no
                     LIMIT 1),
                    'AUTO'
                )
                WHERE sess_id = 'AUTO'
            """)

        # --- Add sess_id column to subject_grades if missing ---
        sg_cols = [r[1] for r in conn.execute("PRAGMA table_info(subject_grades)").fetchall()]
        if 'sess_id' not in sg_cols:
            conn.execute("ALTER TABLE subject_grades ADD COLUMN sess_id TEXT NOT NULL DEFAULT 'AUTO'")
            conn.execute("""
                UPDATE subject_grades
                SET sess_id = COALESCE(
                    (SELECT s.sess_id FROM students s
                     WHERE s.profile_name = subject_grades.profile_name
                       AND s.reg_no = subject_grades.reg_no
                     LIMIT 1),
                    'AUTO'
                )
                WHERE sess_id = 'AUTO'
            """)

        # --- Recreate students with UNIQUE(profile_name, reg_no, sess_id) ---
        students_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='students'"
        ).fetchone()[0]
        if 'UNIQUE(profile_name, reg_no, sess_id)' not in students_sql:
            conn.execute("""
                CREATE TABLE students_v4 (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT NOT NULL,
                    reg_no       INTEGER NOT NULL,
                    name         TEXT,
                    sess_id      TEXT NOT NULL DEFAULT 'AUTO',
                    FOREIGN KEY(profile_name) REFERENCES profiles(name) ON DELETE CASCADE,
                    UNIQUE(profile_name, reg_no, sess_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO students_v4 (id, profile_name, reg_no, name, sess_id)
                SELECT id, profile_name, reg_no, name, COALESCE(NULLIF(sess_id,''), 'AUTO') FROM students
            """)
            conn.execute("DROP TABLE students")
            conn.execute("ALTER TABLE students_v4 RENAME TO students")

        # --- Recreate exam_results with UNIQUE(profile_name, reg_no, exam_id, sess_id) ---
        er_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='exam_results'"
        ).fetchone()[0]
        if 'UNIQUE(profile_name, reg_no, exam_id, sess_id)' not in er_sql:
            conn.execute("""
                CREATE TABLE exam_results_v4 (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name  TEXT NOT NULL,
                    reg_no        INTEGER NOT NULL,
                    exam_id       TEXT NOT NULL,
                    exam_name     TEXT,
                    result_status TEXT,
                    sgpa          REAL DEFAULT 0.0,
                    cgpa          REAL DEFAULT 0.0,
                    raw_json      TEXT,
                    portal_sgpa   REAL,
                    portal_cgpa   REAL,
                    sess_id       TEXT NOT NULL DEFAULT 'AUTO',
                    FOREIGN KEY(profile_name) REFERENCES profiles(name) ON DELETE CASCADE,
                    UNIQUE(profile_name, reg_no, exam_id, sess_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO exam_results_v4
                SELECT id, profile_name, reg_no, exam_id, exam_name, result_status,
                       sgpa, cgpa, raw_json, portal_sgpa, portal_cgpa,
                       COALESCE(NULLIF(sess_id,''), 'AUTO')
                FROM exam_results
            """)
            conn.execute("DROP TABLE exam_results")
            conn.execute("ALTER TABLE exam_results_v4 RENAME TO exam_results")

        # --- Recreate subject_grades with UNIQUE(profile_name, reg_no, subject_code, exam_id, sess_id) ---
        sg_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='subject_grades'"
        ).fetchone()[0]
        if 'UNIQUE(profile_name, reg_no, subject_code, exam_id, sess_id)' not in sg_sql:

            conn.execute("""
                CREATE TABLE subject_grades_v4 (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT NOT NULL,
                    reg_no       INTEGER NOT NULL,
                    exam_id      TEXT NOT NULL,
                    subject_code TEXT NOT NULL,
                    subject_name TEXT,
                    grade_point  REAL DEFAULT 0.0,
                    credit_hours REAL DEFAULT 3.0,
                    sess_id      TEXT NOT NULL DEFAULT 'AUTO',
                    FOREIGN KEY(profile_name) REFERENCES profiles(name) ON DELETE CASCADE,
                    UNIQUE(profile_name, reg_no, subject_code, exam_id, sess_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO subject_grades_v4
                SELECT id, profile_name, reg_no, exam_id, subject_code, subject_name,
                       grade_point, credit_hours,
                       COALESCE(NULLIF(sess_id,''), 'AUTO')
                FROM subject_grades
            """)
            conn.execute("DROP TABLE subject_grades")
            conn.execute("ALTER TABLE subject_grades_v4 RENAME TO subject_grades")

        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        logger.info("Schema v4 migration complete.")


# ---------------------------------------------------------------------------
# Core Upsert Helpers (idempotent — safe to call multiple times)
# ---------------------------------------------------------------------------

def _parse_gp(value) -> float:
    try:
        val = float(value)
        # Multi-layered safeguard: Cap at 4.0 to prevent marks/corrupted data from inflating GPA
        return min(val, 4.0) if val > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def upsert_subject_grades(profile_name: str, reg_no: int, exam_id: str, subjects: list, exam_name: str = None, statement_list: list = None, sess_id: str = 'AUTO'):
    """
    Insert or replace individual subject grades.
    Includes 'Syllabus-Aware' failure inference.
    """
    # 1. Normalize all incoming codes to DEPT-XXXX
    for s in subjects:
        if s.get('code'):
            s['code'] = str(s['code']).strip().upper().replace(' ', '-')

    scraped_codes = {s['code'] for s in subjects if s.get('code')}
    dept = get_dept_from_profile(profile_name)
    dept_map = _credit_map.get(dept, {})
    
    # Identify "Hidden Failures" (In syllabus but not in scrape)
    # CRITICAL: We only infer failure if the subject was found in OTHER students in THIS scan.
    # This prevents mapping subjects from different semesters (e.g. EEE 2101 vs EEE 2109).
    if len(subjects) >= 2:
        # Get common subjects for this specific exam_id & profile to avoid semester bleeding
        with get_connection() as conn:
            common_cur = conn.execute("""
                SELECT subject_code, subject_name, COUNT(*) as occurs
                FROM subject_grades
                WHERE profile_name=? AND exam_id=?
                GROUP BY subject_code
                HAVING occurs >= 3
            """, (profile_name, exam_id))
            exam_subjects = {row[0]: row[1] for row in common_cur.fetchall()}

        for code, name in exam_subjects.items():
            if code not in scraped_codes:
                subjects.append({
                    'code': code,
                    'name': name, # Use the actual name found in other students
                    'grade': 'F', 'gp': 0.0, 'is_inferred': True
                })

    _sess = sess_id or 'AUTO'
    sql = """
        INSERT OR REPLACE INTO subject_grades
        (profile_name, reg_no, exam_id, subject_code, subject_name, grade_point, credit_hours, sess_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    for s in subjects:
        code = str(s.get('code', '')).strip().upper().replace(' ', '-')
        if not code: continue
        subj_name = str(s.get('name', '')).strip()
        gp = _parse_gp(s.get('gp', 0))
        ch = get_subject_credits(code, profile_name, exam_name)
        params = (profile_name, reg_no, exam_id, code, subj_name, gp, ch, _sess)
        
        if statement_list is not None:
            statement_list.append((sql, params))
        else:
            with get_connection() as conn:
                conn.execute(sql, params)


def upsert_exam_result(profile_name: str, res: dict, exam_id: str, exam_name: str, statement_list: list = None, sess_id: str = 'AUTO'):
    """
    Verified Source of Truth: Calculates SGPA locally using verified credits.
    Stores the portal value in 'portal_sgpa' for background auditing.
    """
    reg_no = int(res.get('Registration No', res.get('Reg', 0)))
    raw_sgpa_str = str(res.get('GPA', res.get('SGPA', '-'))).strip()
    raw_cgpa_str = str(res.get('CGPA', '-')).strip()
    
    # Shadow values (what the website claims)
    portal_sgpa = _parse_gp(raw_sgpa_str)
    portal_cgpa = _parse_gp(raw_cgpa_str)
    
    status = str(res.get('Result', res.get('Overall Result', 'Unknown')))
    subjects = res.get('Subjects', [])

    # Local Verification Logic: Calculate SGPA from our mapping
    sgpa = 0.0
    tc = 0.0
    is_mapping_incomplete = False
    
    if subjects:
        tp = 0.0
        for s in subjects:
            code = str(s.get('code', '')).strip().upper().replace(' ', '-')
            gp = _parse_gp(s.get('gp', 0))
            ch = get_subject_credits(code, profile_name, exam_name)
            
            if ch is None:
                is_mapping_incomplete = True
                logger.warning(f"Unknown subject observed: {code} in {profile_name}. Calibration needed.")
                break
            tp += gp * ch
            tc += ch
        
        if not is_mapping_incomplete and tc > 0:
            sgpa = round(tp / tc, 2)
            
            # Shadow Audit: Logging drift between local math and portal math
            if raw_sgpa_str not in ['-', '', 'None'] and abs(sgpa - portal_sgpa) > 0.01:
                logger.warning(f"Credit Drift Detected [Reg {reg_no} | {profile_name}]: Portal says {portal_sgpa}, We calculated {sgpa}.")
        else:
            # Fallback to portal SGPA IF we can't calculate it locally (mapping missing)
            sgpa = portal_sgpa
    else:
        # Fallback if no subjects list was extracted at all
        sgpa = portal_sgpa

    # CGPA remains primarily portal-sourced as it requires multi-exam history
    cgpa = portal_cgpa

    _sess = sess_id or 'AUTO'
    sql = """
        INSERT OR REPLACE INTO exam_results
            (profile_name, reg_no, exam_id, exam_name, result_status, sgpa, cgpa, portal_sgpa, portal_cgpa, raw_json, sess_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (profile_name, reg_no, exam_id, exam_name, status, sgpa, cgpa, portal_sgpa, portal_cgpa, json.dumps(res), _sess)

    if statement_list is not None:
        statement_list.append((sql, params))
    else:
        with get_connection() as conn:
            conn.execute(sql, params)

    # Now upsert subject grades
    upsert_subject_grades(profile_name, reg_no, exam_id, subjects, exam_name, statement_list, sess_id=_sess)


def upsert_student(profile_name: str, reg_no: int, name: str, sess_id: str, statement_list: list = None):
    """Idempotent student upsert — keyed by (profile_name, reg_no, sess_id)."""
    sess_id = sess_id or 'AUTO'
    sql = """
        INSERT INTO students (profile_name, reg_no, name, sess_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(profile_name, reg_no, sess_id) DO UPDATE SET name=excluded.name
    """
    params = (profile_name, reg_no, name, sess_id)
    if statement_list is not None:
        statement_list.append((sql, params))
    else:
        with get_connection() as conn:
            conn.execute(sql, params)


def update_scan_log(profile_name: str, exam_id: str, student_count: int, statement_list: list = None):
    sql = """
        INSERT OR REPLACE INTO scan_log (profile_name, exam_id, scanned_at, student_count)
        VALUES (?, ?, ?, ?)
    """
    params = (profile_name, exam_id, time.time(), student_count)
    if statement_list is not None:
        statement_list.append((sql, params))
    else:
        with get_connection() as conn:
            conn.execute(sql, params)



def should_rescan(profile_name: str, exam_id: str, interval_minutes: int) -> bool:
    """Return True if this exam hasn't been scanned within interval_minutes."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT scanned_at FROM scan_log WHERE profile_name=? AND exam_id=?",
            (profile_name, exam_id)
        )
        row = cur.fetchone()
        if row is None:
            return True
        return (time.time() - row[0]) >= (interval_minutes * 60)


def save_profile_and_results(profile_name: str, pro_id: str, sess_id: str,
                              results_list: list, exam_id: str, exam_name: str):
    """
    Saves a newly scraped batch as a new profile.
    Uses BATCHING for cloud performance.
    """
    stmts = []
    stmts.append((
        "INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)",
        (profile_name, pro_id, sess_id, time.time())
    ))

    for res in results_list:
        reg_no = int(res.get('Registration No', res.get('Reg', 0)))
        student_name = str(res.get('Name', res.get('Student Name', 'Unknown')))
        student_sess = str(res.get('_sess_id', sess_id))
        upsert_student(profile_name, reg_no, student_name, student_sess, stmts)
        upsert_exam_result(profile_name, res, exam_id, exam_name, stmts, sess_id=student_sess)

    update_scan_log(profile_name, exam_id, len(results_list), stmts)

    with get_connection() as conn:
        if hasattr(conn, 'batch'):
            conn.batch(stmts)
        else:
            # Fallback for sqlite3 (sequential)
            for sql, params in stmts:
                conn.execute(sql, params)
    return True


def save_exam_analytics_only(profile_name: str, exam_id: str, exam_name: str, results_list: list):
    """
    Saves ONLY exam results (and subject grades) for an existing profile.
    Uses BATCHING for cloud performance.
    """
    stmts = []
    for res in results_list:
        student_sess = str(res.get('_sess_id', 'AUTO'))
        upsert_exam_result(profile_name, res, exam_id, exam_name, stmts, sess_id=student_sess)
    update_scan_log(profile_name, exam_id, len(results_list), stmts)

    with get_connection() as conn:
        if hasattr(conn, 'batch'):
            conn.batch(stmts)
        else:
            for sql, params in stmts:
                conn.execute(sql, params)
    return True


def update_profile_metadata(name: str, pro_id: str = None, sess_id: str = None):
    """Updates only the metadata fields for an existing profile."""
    with get_connection() as conn:
        if pro_id and sess_id:
            conn.execute("UPDATE profiles SET pro_id=?, sess_id=? WHERE name=?", (pro_id, sess_id, name))
        elif pro_id:
            conn.execute("UPDATE profiles SET pro_id=? WHERE name=?", (pro_id, name))
        elif sess_id:
            conn.execute("UPDATE profiles SET sess_id=? WHERE name=?", (sess_id, name))
        conn.commit()


def remove_student_from_profile(profile_name: str, reg_no: int, sess_id: str):
    """Removes a student and all their associated results from a profile."""
    with get_connection() as conn:
        conn.execute("DELETE FROM subject_grades WHERE profile_name=? AND reg_no=? AND sess_id=?", (profile_name, reg_no, sess_id))
        conn.execute("DELETE FROM exam_results WHERE profile_name=? AND reg_no=? AND sess_id=?", (profile_name, reg_no, sess_id))
        conn.execute("DELETE FROM students WHERE profile_name=? AND reg_no=? AND sess_id=?", (profile_name, reg_no, sess_id))
        conn.commit()

# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------

def get_profiles() -> dict:
    """Returns dict keyed by profile name, compatible with legacy app.py usage."""
    profiles = {}
    try:
        with get_connection() as conn:
            cur = conn.execute("SELECT name, pro_id, sess_id, timestamp FROM profiles")
            for p_name, pro_id, sess_id, ts in cur.fetchall():
                stu_cur = conn.execute(
                    "SELECT reg_no, sess_id, name FROM students WHERE profile_name=?", (p_name,)
                )
                regs = [[r[0], r[1], r[2]] for r in stu_cur.fetchall()]
                profiles[p_name] = {
                    "pro_id": pro_id,
                    "sess_id": sess_id,
                    "timestamp": ts,
                    "regs": regs,
                }
    except Exception as e:
        logger.error("get_profiles error: %s", e)
    return profiles


def get_effective_cgpa_per_student(profile_name: str) -> list:
    """
    Retake-aware CGPA calculation.
    For each student in the profile, for each subject, takes the BEST grade_point
    ever recorded across ALL exams. Then computes weighted GPA from those bests.
    Returns list of dicts: {reg_no, name, effective_cgpa, raw_cgpa, improvement_count}
    """
    results = []
    with get_connection() as conn:
        # Get all students in this profile
        students_cur = conn.execute(
            "SELECT reg_no, name, sess_id FROM students WHERE profile_name=?", (profile_name,)
        )
        students = students_cur.fetchall()

        for reg_no, name, sess_id in students:
            # Get best grade per subject across all exams for this student
            best_cur = conn.execute("""
                SELECT subject_code, MAX(grade_point) as best_gp, credit_hours
                FROM subject_grades
                WHERE profile_name=? AND reg_no=? AND sess_id=?
                GROUP BY subject_code
            """, (profile_name, reg_no, sess_id))
            best_grades = best_cur.fetchall()

            if not best_grades:
                continue

            # Weighted GPA: sum(gp * ch) / sum(ch)
            total_points = sum((row[1] or 0.0) * (row[2] if row[2] is not None else 3.0) for row in best_grades)
            total_credits = sum((row[2] if row[2] is not None else 3.0) for row in best_grades)
            effective_cgpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

            # Calculate Improvement/Retake counts based on defined thresholds
            # Improvement: 2.0 <= GP <= 2.75
            # Retake: GP < 2.0 (Fail)
            improvement_count = sum(1 for row in best_grades if 2.0 <= row[1] <= 2.75)
            retake_count = sum(1 for row in best_grades if row[1] < 2.0)

            # First-Chance Failure Detection: 
            # Did they have ANY grade < 2.0 in any attempt for this profile?
            fail_check_cur = conn.execute("""
                SELECT COUNT(*) FROM subject_grades 
                WHERE profile_name=? AND reg_no=? AND sess_id=? AND grade_point < 2.0
            """, (profile_name, reg_no, sess_id))
            has_ever_failed = fail_check_cur.fetchone()[0] > 0

            # Latest raw CGPA from exam_results for comparison
            raw_cur = conn.execute("""
                SELECT cgpa, result_status FROM exam_results
                WHERE profile_name=? AND reg_no=? AND sess_id=?
                ORDER BY exam_id DESC LIMIT 1
            """, (profile_name, reg_no, sess_id))
            raw_row = raw_cur.fetchone()
            raw_cgpa = round(raw_row[0], 2) if raw_row else 0.0
            
            # Robust mapping for Pass/Fail detection
            db_status = str(raw_row[1]) if raw_row else "Unknown"
            if "Promoted" in db_status or "Passed" in db_status or "P" == db_status:
                status = "Passed/Promoted"
            elif "Failed" in db_status or "Withheld" in db_status:
                status = "Failed/Withheld"
            else:
                # If CGPA is > 0, they likely passed but status was missing in portal
                status = "Passed/Promoted" if effective_cgpa > 0 else "Unknown"

            results.append({
                "reg_no": reg_no,
                "sess_id": sess_id,
                "name": name,
                "effective_cgpa": effective_cgpa,
                "raw_cgpa": raw_cgpa,
                "result_status": status,
                "improvement_count": improvement_count,
                "retake_count": retake_count,
                "first_chance_fail": has_ever_failed
            })

    results.sort(key=lambda x: x["effective_cgpa"], reverse=True)
    return results




# ---------------------------------------------------------------------------
# Per-Exam Scoped Functions (Semester-Isolated Analytics)
# ---------------------------------------------------------------------------

def get_exams_for_profile(profile_name: str) -> list:
    """
    Returns all exams ingested for a profile, sorted latest-first (by exam_id DESC).
    Each entry = {exam_id, exam_name, scanned_at, student_count}
    """
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT sl.exam_id, er.exam_name, sl.scanned_at, sl.student_count
            FROM scan_log sl
            LEFT JOIN (
                SELECT exam_id, exam_name FROM exam_results
                WHERE profile_name=?
                GROUP BY exam_id
            ) er ON sl.exam_id = er.exam_id
            WHERE sl.profile_name=?
            ORDER BY CAST(sl.exam_id AS INTEGER) DESC
        """, (profile_name, profile_name))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_student_data_for_exam(profile_name: str, exam_id: str) -> list:
    """
    Returns per-student analytics strictly scoped to one exam (semester).
    - sgpa: from raw_json['GPA'] (semester GPA as reported by portal)
    - cgpa: from exam_results.cgpa (cumulative since semester 1, as stored by the portal)
    - first_chance_fail: True if the student has any grade < 2.0 IN THIS EXAM
    - improvement_count: subjects with 2.0 <= gp <= 2.75 IN THIS EXAM
    - retake_count: subjects with gp < 2.0 IN THIS EXAM
    No cross-semester data is used.
    """
    results = []
    with get_connection() as conn:
        # Pull raw_json so we can extract GPA (sgpa) which may be 0 in the sgpa column for legacy rows
        students_cur = conn.execute("""
            SELECT s.reg_no, s.name, er.sgpa, er.cgpa, er.result_status, er.raw_json, s.sess_id
            FROM students s
            JOIN exam_results er ON s.profile_name = er.profile_name
                                AND s.reg_no = er.reg_no
                                AND s.sess_id = er.sess_id
            WHERE s.profile_name=? AND er.exam_id=?
        """, (profile_name, exam_id))
        students = students_cur.fetchall()

        for reg_no, name, sgpa_col, cgpa, db_status, raw_json_str, sess_id in students:
            # Subject grades FOR THIS EXAM ONLY
            grades_cur = conn.execute("""
                SELECT subject_code, grade_point, credit_hours
                FROM subject_grades
                WHERE profile_name=? AND reg_no=? AND exam_id=?
            """, (profile_name, reg_no, exam_id))
            grades = grades_cur.fetchall()

            if not grades:
                continue

            improvement_count = sum(1 for _, gp, _ in grades if 2.0 <= gp <= 2.75)
            retake_count      = sum(1 for _, gp, _ in grades if gp < 2.0)
            first_chance_fail = retake_count > 0

            # Extract SGPA: prefer raw_json GPA field (always stored correctly by scraper)
            sgpa = sgpa_col
            raw_sgpa_str = None
            raw_cgpa_str = None
            if raw_json_str:
                try:
                    raw = json.loads(raw_json_str)
                    raw_sgpa_str = str(raw.get('GPA', raw.get('SGPA', '-')))
                    raw_cgpa_str = str(raw.get('CGPA', '-'))
                    if sgpa == 0.0:
                        sgpa = _parse_gp(raw_sgpa_str)
                except Exception:
                    pass

            # Fallback for missing SGPA IFF it was truly omitted in the scrape
            if sgpa == 0.0 and grades and (raw_sgpa_str in ['-', '', 'None']):
                total_points = sum(gp * ch for _, gp, ch in grades)
                total_credits = sum(ch for _, _, ch in grades)
                if total_credits > 0:
                    sgpa = round(total_points / total_credits, 2)

            # Fallback for missing CGPA IFF it was truly omitted in the scrape
            if (cgpa is None or cgpa == 0.0) and (raw_cgpa_str in ['-', '', 'None']):
                # Dynamically calculate the retake-aware CGPA up to this specific exam instance
                try:
                    calc_cur = conn.execute("""
                        SELECT MAX(grade_point), credit_hours
                        FROM subject_grades
                        WHERE profile_name=? AND reg_no=? AND CAST(exam_id AS INTEGER) <= ?
                        GROUP BY subject_code
                    """, (profile_name, reg_no, int(exam_id)))
                    best_grades = calc_cur.fetchall()
                    if best_grades:
                        total_cgpa_points = sum(gp * ch for gp, ch in best_grades if ch > 0)
                        total_cgpa_credits = sum(ch for gp, ch in best_grades if ch > 0)
                        if total_cgpa_credits > 0:
                            cgpa = round(total_cgpa_points / total_cgpa_credits, 2)
                except ValueError:
                    # If exam_id happens to be non-integer, skip historical filter
                    pass

            # Robust status mapping
            db_status = str(db_status)
            if "Promoted" in db_status or "Passed" in db_status or db_status == "P":
                status = "Passed/Promoted"
            elif "Failed" in db_status or "Withheld" in db_status:
                status = "Failed/Withheld"
            else:
                status = "Passed/Promoted" if (cgpa or 0) > 0 else "Unknown"

            results.append({
                "reg_no":            reg_no,
                "sess_id":           sess_id,
                "name":              name,
                "sgpa":              round(float(sgpa  or 0), 2),
                "cgpa":              round(float(cgpa  or 0), 2),
                "result_status":     status,
                "improvement_count": improvement_count,
                "retake_count":      retake_count,
                "first_chance_fail": first_chance_fail,
            })

    results.sort(key=lambda x: x["cgpa"], reverse=True)
    return results


def get_subject_data_for_exam(profile_name: str, exam_id: str) -> list:
    """
    Returns flat subject-grade rows for one specific exam.
    Useful for boxplots, heatmaps, clustering, difficulty ranking.
    """
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT sg.reg_no, s.name, sg.subject_code, sg.subject_name,
                   sg.grade_point as gp, sg.credit_hours
            FROM subject_grades sg
            JOIN students s ON sg.profile_name = s.profile_name
                           AND sg.reg_no = s.reg_no
                           AND sg.sess_id = s.sess_id
            WHERE sg.profile_name=? AND sg.exam_id=?
        """, (profile_name, exam_id))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]



# ---------------------------------------------------------------------------
# Deep Analysis Engine (Precise Credit-Weighted Computation)
# ---------------------------------------------------------------------------

def get_semester_from_code(code: str, dept: str) -> int:
    """
    Derives the absolute semester number (1–8) from a subject code.
    CSE/EEE use 4-digit codes: DEPT-XYZZ → semester = (X-1)*2 + Y
    Civil uses 3-digit codes: DEPT-XYZ → semester = X
    Returns 0 if unable to parse.
    """
    parts = code.strip().upper().replace(' ', '-').split('-')
    if len(parts) != 2:
        return 0
    num_str = parts[1].rstrip('*')  # strip trailing asterisks
    if not num_str or not num_str[0].isdigit():
        return 0

    if dept == "Civil":
        # Civil: 3-digit codes like CE-101 → first digit = semester
        try:
            return int(num_str[0])
        except (ValueError, IndexError):
            return 0
    else:
        # CSE/EEE: 4-digit codes like CSE-1101 → (digit1-1)*2 + digit2
        if len(num_str) < 2:
            return 0
        try:
            year = int(num_str[0])
            sem_within_year = int(num_str[1])
            if 1 <= year <= 4 and sem_within_year in (1, 2):
                return (year - 1) * 2 + sem_within_year
        except (ValueError, IndexError):
            pass
        return 0


def get_semester_total_credits(dept: str, semester_num: int) -> float:
    """
    Returns the standard required total credits for a given semester (1-8).
    This avoids the over-counting bug where summing all subjects in credit_mapping.json 
    would accidentally sum all elective options (causing 4th year to report 90+ credits).
    """
    STANDARD_CREDITS = {
        "CSE": {
            1: 20.5, 2: 21.5, 3: 22.25, 4: 19.25,
            5: 19.5, 6: 19.5, 7: 20.5, 8: 17.5
        },
        "Civil": {
            1: 20.25, 2: 20.75, 3: 21.0, 4: 20.5,
            5: 20.5, 6: 20.5, 7: 19.0, 8: 17.5
        },
        "EEE": {
            1: 21.0, 2: 22.5, 3: 21.0, 4: 19.5,
            5: 21.0, 6: 19.5, 7: 21.0, 8: 16.5
        }
    }
    
    dept_map = STANDARD_CREDITS.get(dept, STANDARD_CREDITS["CSE"])
    return dept_map.get(semester_num, 0.0)


# Hardcoded clean curriculum for CSE semesters that have elective over-count.
# Structure: {'code': str, 'credit': float, 'is_elective': bool, 'label': str}
_CSE_ELECTIVE_SEMESTERS = {
    7: {
        'core': [
            {'code': 'CSE-4101', 'credit': 3.0},
            {'code': 'CSE-4102', 'credit': 3.0},
            {'code': 'CSE-4111', 'credit': 1.5},
            {'code': 'CSE-4113', 'credit': 1.5},
            {'code': 'CSE-4114', 'credit': 2.0},
            {'code': 'SS-4103',  'credit': 2.0},
        ],
        'elective_slots': [
            {'code': 'ELEC-7-T1', 'credit': 3.0, 'label': 'Elective Theory I'},
            {'code': 'ELEC-7-T2', 'credit': 3.0, 'label': 'Elective Theory II'},
            {'code': 'ELEC-7-L1', 'credit': 1.5, 'label': 'Elective Lab I'},
        ],
    },
    8: {
        'core': [
            {'code': 'CSE-4202', 'credit': 2.0},
            {'code': 'CSE-4203', 'credit': 2.0},
            {'code': 'CSE-4214', 'credit': 4.0},
            {'code': 'ECO-4201', 'credit': 2.0},
        ],
        'elective_slots': [
            {'code': 'ELEC-8-T1', 'credit': 3.0, 'label': 'Elective Theory I'},
            {'code': 'ELEC-8-T2', 'credit': 3.0, 'label': 'Elective Theory II'},
            {'code': 'ELEC-8-L1', 'credit': 1.5, 'label': 'Elective Lab I'},
        ],
    },
}

def get_semester_courses(dept: str, semester_num: int) -> list[dict]:
    """
    Returns a clean course list for a semester.
    Each entry: {'code': str, 'credit': float, 'is_elective': bool, 'label': str, 'name': str}

    For CSE sems 7 & 8: returns confirmed core courses + 3 named elective slots
    (2 theory × 3.0 cr + 1 lab × 1.5 cr) instead of all 30+ elective variants.
    For all other sems: derives courses from credit_mapping.json directly
    (those semesters have exact 1:1 mappings — no over-count issue).
    """
    # Fetch names mapping from database (department-aware and frequency-based)
    code_to_name = {
        'CSE-4203': 'Engineering Ethics'
    }
    try:
        with get_connection() as conn:
            # Query the names for the given department, sorting by frequency so the most common one wins
            query = """
                SELECT subject_code, subject_name, COUNT(*) as c 
                FROM subject_grades 
                WHERE subject_name IS NOT NULL 
                  AND subject_name != '' 
                  AND LOWER(profile_name) LIKE ?
                GROUP BY subject_code, subject_name 
                ORDER BY c ASC
            """
            cur = conn.execute(query, (f'%{dept.lower()}%',))
            for r in cur:
                code_to_name[r[0]] = r[1]
    except Exception:
        pass

    if dept == 'CSE' and semester_num in _CSE_ELECTIVE_SEMESTERS:
        sem_def = _CSE_ELECTIVE_SEMESTERS[semester_num]
        result = []
        for c in sem_def['core']:
            name = code_to_name.get(c['code'], '')
            result.append({'code': c['code'], 'credit': c['credit'],
                           'is_elective': False, 'label': c['code'], 'name': name})
        for slot in sem_def['elective_slots']:
            result.append({'code': slot['code'], 'credit': slot['credit'],
                           'is_elective': True, 'label': slot['label'], 'name': ''})
        return result

    # For semesters 1-6 (and EEE/Civil): derive directly — no elective over-count
    dept_map = _credit_map.get(dept, {})
    courses = []
    for code, credit in dept_map.items():
        if get_semester_from_code(code, dept) == semester_num:
            name = code_to_name.get(code, '')
            courses.append({'code': code, 'credit': credit,
                            'is_elective': False, 'label': code, 'name': name})
    courses.sort(key=lambda c: c['code'])
    return courses

def compute_graduation_cgpa_from_inputs(
    adj_cgpa: float,
    adj_credits: float,
    remaining_semester_inputs: list[dict],
    dept: str,
) -> dict:
    """
    Computes projected graduation CGPA from user-provided semester inputs.

    remaining_semester_inputs: list of dicts, one per remaining semester:
        {
            'semester': int,                    # absolute semester number (1-8)
            'mode': 'summary' | 'detailed',     # input mode
            'sgpa': float | None,               # if mode='summary', the expected SGPA
            'course_grades': list[dict] | None,  # if mode='detailed', list of
                                                 #   {'code': str, 'credit': float, 'gp': float}
        }

    Returns:
        {
            'graduation_cgpa': float,
            'total_new_points': float,
            'total_new_credits': float,
            'per_semester_detail': list[dict],  # [{semester, sgpa, credits, points}, ...]
            'grand_total_credits': float,
            'grand_total_points': float,
        }
    """
    adj_points = adj_cgpa * adj_credits
    total_new_points = 0.0
    total_new_credits = 0.0
    per_semester_detail = []

    for sem_input in remaining_semester_inputs:
        sem_num = sem_input['semester']
        mode = sem_input.get('mode', 'summary')
        sem_credits = get_semester_total_credits(dept, sem_num)

        if mode == 'detailed' and sem_input.get('course_grades'):
            # Calculate SGPA from individual course grades
            course_points = 0.0
            course_credits = 0.0
            for cg in sem_input['course_grades']:
                if cg.get('gp', 0) > 0 or cg.get('credit', 0) > 0:
                    course_points += cg['gp'] * cg['credit']
                    course_credits += cg['credit']

            if course_credits > 0:
                calculated_sgpa = round(course_points / course_credits, 2)
            else:
                calculated_sgpa = 0.0

            # Use the actual credits filled in for the CGPA calculation
            # (handles elective subsets correctly)
            sem_points = course_points
            effective_credits = course_credits
        else:
            # Summary mode: use input SGPA × standard semester credits
            sgpa = sem_input.get('sgpa', 0.0) or 0.0
            calculated_sgpa = sgpa
            sem_points = sgpa * sem_credits
            effective_credits = sem_credits

        total_new_points += sem_points
        total_new_credits += effective_credits
        per_semester_detail.append({
            'semester': sem_num,
            'sgpa': round(calculated_sgpa, 2),
            'credits': round(effective_credits, 1),
            'points': round(sem_points, 2),
        })

    grand_total_credits = adj_credits + total_new_credits
    grand_total_points = adj_points + total_new_points
    graduation_cgpa = round(grand_total_points / grand_total_credits, 2) if grand_total_credits > 0 else 0.0

    return {
        'graduation_cgpa': graduation_cgpa,
        'total_new_points': round(total_new_points, 2),
        'total_new_credits': round(total_new_credits, 1),
        'per_semester_detail': per_semester_detail,
        'grand_total_credits': round(grand_total_credits, 1),
        'grand_total_points': round(grand_total_points, 2),
    }


def compute_deep_analysis(raw_records: list, profile_name: str, current_exam_label: str) -> dict:
    """
    Processes a student's full academic history (raw portal records) to compute:
    - True CGPA (credit-weighted, considering retake improvements)
    - Pending retakes (subjects still failing after all attempts)
    - Precise target SGPA for next semester

    Rules:
    1. Main semester exams: grouped by semester label, latest exam_id wins
       (handles readd students — current batch exam supersedes old batch).
    2. Retake/improvement exams: applied only if the grade is STRICTLY BETTER
       than the current effective grade for that subject.
    3. Target SGPA: computed using actual next-semester credit weight, not
       the old 1.1 approximation.
    """
    dept = get_dept_from_profile(profile_name)

    RETAKE_KEYWORDS = [
        "retake", "re-take", "improvement", "special",
        "make-up", "makeup", "supplementary"
    ]
    SEM_PATTERN = re.compile(
        r'(\d+(?:st|nd|rd|th)\s+year\s+\d+(?:st|nd|rd|th)\s+semester)',
        re.IGNORECASE
    )

    # --- Step 1: Classify records into main vs retake ---
    main_records = []
    retake_records = []
    for rec in raw_records:
        ename = rec.get('_exam_name', '')
        if any(kw in ename.lower() for kw in RETAKE_KEYWORDS):
            retake_records.append(rec)
        else:
            main_records.append(rec)

    # --- Step 2: Group main exams by semester, keep latest exam_id ---
    semester_groups = {}  # sem_label -> (exam_id_int, record)
    for rec in main_records:
        ename = rec.get('_exam_name', '')
        m = SEM_PATTERN.search(ename)
        sem_label = m.group(1).lower().strip() if m else ename.lower().strip()

        try:
            eid_int = int(rec.get('_exam_id', 0))
        except (ValueError, TypeError):
            eid_int = 0

        if sem_label not in semester_groups:
            semester_groups[sem_label] = (eid_int, rec)
        else:
            current_eid, _ = semester_groups[sem_label]
            if eid_int > current_eid:
                semester_groups[sem_label] = (eid_int, rec)

    # --- Step 2.5: Filter voided future semesters for readmitted students ---
    # A student's current progression is dictated by their MOST RECENT main exam.
    # Any main exams from older batches that are for a higher semester are voided.
    def _get_abs_sem(rec):
        dept = profile_name.split()[0] if profile_name else 'CSE'
        for subj in rec.get('Subjects', []):
            code = str(subj.get('code', '')).strip()
            s = get_semester_from_code(code, dept)
            if s > 0: return s
        return 0

    global_max_eid = 0
    current_progression_sem = 0
    for sem_label, (eid_int, rec) in semester_groups.items():
        if eid_int > global_max_eid:
            global_max_eid = eid_int
            current_progression_sem = _get_abs_sem(rec)

    if current_progression_sem > 0:
        valid_groups = {}
        for sem_label, (eid_int, rec) in semester_groups.items():
            if _get_abs_sem(rec) <= current_progression_sem:
                valid_groups[sem_label] = (eid_int, rec)
        semester_groups = valid_groups

    # --- Step 3: Build effective grades from winning main exams ---
    effective_grades = {}  # code -> {gp, credit, source}
    for sem_label, (eid_int, rec) in semester_groups.items():
        ename = rec.get('_exam_name', '')
        for subj in rec.get('Subjects', []):
            code = str(subj.get('code', '')).strip().upper().replace(' ', '-')
            if not code:
                continue
            try:
                gp = min(float(subj.get('gp', 0)), 4.0)
                if gp < 0:
                    gp = 0.0
            except (ValueError, TypeError):
                gp = 0.0

            credit = get_subject_credits(code, profile_name, ename)
            if credit is None:
                credit = 3.0  # fallback for unmapped subjects

            effective_grades[code] = {
                'gp': gp,
                'credit': credit,
                'source': 'main',
                'exam_id': eid_int,
                'name': subj.get('name', '')
            }

    # --- Step 4: Apply retake improvements (only if strictly better) ---
    retake_records.sort(key=lambda r: int(r.get('_exam_id', 0) or 0))
    for rec in retake_records:
        for subj in rec.get('Subjects', []):
            code = str(subj.get('code', '')).strip().upper().replace(' ', '-')
            if not code:
                continue
            try:
                gp = min(float(subj.get('gp', 0)), 4.0)
                if gp < 0:
                    gp = 0.0
            except (ValueError, TypeError):
                gp = 0.0

            if code in effective_grades:
                original_gp = effective_grades[code]['gp']
                # Only apply if retake grade is strictly better
                if gp > original_gp:
                    # Classify based on the ORIGINAL grade, not the exam name:
                    # - Original GP < 2.0 (was failing) → retake to clear
                    # - Original GP >= 2.0 (was passing) → improvement to boost
                    clear_type = (
                        'improvement_cleared' if original_gp >= 2.0
                        else 'retake_cleared'
                    )
                    effective_grades[code]['gp'] = gp
                    effective_grades[code]['source'] = clear_type
            # else: subject only in retake but not in any main exam → skip
            # (this avoids counting subjects from a different batch's curriculum)

    # --- Step 5: Calculate true CGPA ---
    total_points = sum(g['gp'] * g['credit'] for g in effective_grades.values())
    total_credits = sum(g['credit'] for g in effective_grades.values())
    true_cgpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

    # --- Step 6: Get official CGPA from the latest main exam for comparison ---
    official_cgpa = 0.0
    latest_main_eid = 0
    for sem_label, (eid_int, rec) in semester_groups.items():
        if eid_int > latest_main_eid:
            latest_main_eid = eid_int
            try:
                official_cgpa = round(float(rec.get('CGPA', 0) or 0), 2)
            except (ValueError, TypeError):
                official_cgpa = 0.0

    cgpa_diff = round(true_cgpa - official_cgpa, 2)

    # --- Step 7: Identify pending retakes (GP < 2.0 = still failing) ---
    pending_retakes = []
    for code, g in effective_grades.items():
        if g['gp'] < 2.0:
            pending_retakes.append({
                'code': code,
                'gp': g['gp'],
                'credit': g['credit'],
                'source': g['source']
            })
    pending_retakes.sort(key=lambda x: x['code'])

    # --- Step 8: Calculate precise target SGPA ---
    # Parse current semester from exam label
    yr_match = re.search(r'(\d)[a-z]{2}\s*Yr', current_exam_label, re.IGNORECASE)
    sem_match = re.search(r'(\d)[a-z]{2}\s*Sem', current_exam_label, re.IGNORECASE)

    precise_target_sgpa = 0.0
    next_sem_credits = 0.0
    promo_target = None
    current_abs_sem = 0

    if yr_match and sem_match:
        yr = int(yr_match.group(1))
        sem_in_yr = int(sem_match.group(1))
        current_abs_sem = (yr - 1) * 2 + sem_in_yr
        next_abs_sem = current_abs_sem + 1

        # Promotion thresholds
        if yr == 1: promo_target = 2.00
        elif yr == 2: promo_target = 2.25
        elif yr == 3: promo_target = 2.50
        elif yr == 4: promo_target = 2.75

        # Only compute target if we're on an odd semester (promotion check is at year-end)
        is_even_sem = (sem_in_yr == 2)
        if promo_target is not None and not is_even_sem and next_abs_sem <= 8:
            next_sem_credits = get_semester_total_credits(dept, next_abs_sem)
            if next_sem_credits > 0 and total_credits > 0:
                precise_target_sgpa = (
                    promo_target * (total_credits + next_sem_credits) -
                    true_cgpa * total_credits
                ) / next_sem_credits
                precise_target_sgpa = max(0.0, round(precise_target_sgpa, 2))

    return {
        'true_cgpa': true_cgpa,
        'official_cgpa': official_cgpa,
        'cgpa_diff': cgpa_diff,
        'total_credits': total_credits,
        'semesters_found': len(semester_groups),
        'current_semester': current_abs_sem,
        'promo_target': promo_target,
        'pending_retakes': pending_retakes,
        'pending_retake_count': len(pending_retakes),
        'precise_target_sgpa': precise_target_sgpa,
        'next_sem_credits': next_sem_credits,
        'effective_grade_count': len(effective_grades),
        'effective_grades': effective_grades,
        'retake_records': retake_records,
    }


def compute_graduation_projection(
    deep_result: dict,
    target_grad_cgpa: float,
    dept: str,
    total_semesters: int = 8,
) -> dict:
    """
    Given the output of compute_deep_analysis() and a user target graduation CGPA,
    calculates the minimum average SGPA required across ALL remaining semesters.

    Math:
        current_points    = true_cgpa * total_credits_completed
        remaining_credits = sum(get_semester_total_credits(dept, sem)
                            for sem in range(current_semester+1, total_semesters+1))
        required_avg_sgpa = (target_grad_cgpa * (total_credits + remaining_credits)
                            - current_points) / remaining_credits
    """
    true_cgpa        = deep_result.get("true_cgpa", 0.0)
    total_credits    = deep_result.get("total_credits", 0.0)
    current_semester = deep_result.get("current_semester", 0)

    current_points = true_cgpa * total_credits

    # Build per-semester remaining credit breakdown
    remaining_breakdown = []
    remaining_credits   = 0.0
    for sem in range(current_semester + 1, total_semesters + 1):
        sem_cr = get_semester_total_credits(dept, sem)
        if sem_cr > 0:
            remaining_breakdown.append({"semester": sem, "credits": sem_cr})
            remaining_credits += sem_cr

    # Edge case: no remaining semesters (graduated / final sem)
    if remaining_credits <= 0:
        already_met = true_cgpa >= target_grad_cgpa
        return {
            "target_cgpa": target_grad_cgpa,
            "current_true_cgpa": true_cgpa,
            "credits_completed": total_credits,
            "remaining_semesters": 0,
            "remaining_credits": 0.0,
            "remaining_credits_breakdown": [],
            "required_avg_sgpa": 0.0,
            "is_achievable": already_met,
            "already_met": already_met,
            "deficit_points": 0.0,
        }

    total_all_credits = total_credits + remaining_credits
    required_points   = target_grad_cgpa * total_all_credits - current_points
    required_avg_sgpa = round(required_points / remaining_credits, 2)

    already_met = required_avg_sgpa <= 0.0

    return {
        "target_cgpa": target_grad_cgpa,
        "current_true_cgpa": true_cgpa,
        "credits_completed": total_credits,
        "remaining_semesters": len(remaining_breakdown),
        "remaining_credits": round(remaining_credits, 1),
        "remaining_credits_breakdown": remaining_breakdown,
        "required_avg_sgpa": required_avg_sgpa,
        "is_achievable": required_avg_sgpa <= 4.0,
        "already_met": already_met,
        "deficit_points": 0.0,
    }


def compute_advanced_projection(
    deep_result: dict,
    effective_grades: dict,
    retake_records: list,
    retake_clear_gp: float = 2.0,
    improvement_target_gp: float | None = None,
) -> dict:
    """
    Computes advanced projection details including retake clears and improvement eligibility.
    """
    attempted_subjects = {}
    for rec in retake_records:
        for subj in rec.get('Subjects', []):
            code = str(subj.get('code', '')).strip().upper().replace(' ', '-')
            if not code: continue
            gp = min(float(subj.get('gp', 0) or 0), 4.0)
            eid = int(rec.get('_exam_id', 0) or 0)
            if code not in attempted_subjects:
                attempted_subjects[code] = []
            attempted_subjects[code].append({'gp': gp, 'exam_id': eid})

    pending_retakes = []
    improvement_candidates = []
    already_attempted = []
    ineligible_retake_cleared = []

    total_points = deep_result['true_cgpa'] * deep_result['total_credits']
    total_credits = deep_result['total_credits']
    
    projected_points_retakes = total_points
    projected_points_all = total_points

    for code, g in effective_grades.items():
        curr_gp = g['gp']
        credit = g['credit']
        source = g['source']
        subj_name = g.get('name', '')

        if curr_gp < 2.0:
            simulated_gp = retake_clear_gp
            cgpa_impact = ((simulated_gp - curr_gp) * credit) / total_credits if total_credits > 0 else 0
            pending_retakes.append({
                'code': code, 'name': subj_name, 'current_gp': curr_gp, 'credit': credit,
                'simulated_gp': simulated_gp, 'cgpa_impact': cgpa_impact
            })
            projected_points_retakes += (simulated_gp - curr_gp) * credit
            projected_points_all += (simulated_gp - curr_gp) * credit
        elif source in ('retake_cleared', 'improvement_cleared', 'retake_improved'):
            if source == 'improvement_cleared':
                reason = "Cleared via improvement \u2014 cannot improve again"
            else:
                reason = "Cleared via retake \u2014 cannot improve"
            ineligible_retake_cleared.append({
                'code': code, 'name': subj_name, 'current_gp': curr_gp, 'credit': credit,
                'reason': reason, 'clear_type': source
            })
        elif 2.0 <= curr_gp <= 2.75:
            if code in attempted_subjects:
                attempt_gp = max((a['gp'] for a in attempted_subjects[code]), default=0)
                already_attempted.append({
                    'code': code, 'name': subj_name, 'current_gp': curr_gp, 'credit': credit,
                    'attempt_gp': attempt_gp, 'reason': "Already improved once"
                })
            else:
                improvement_candidates.append({
                    'code': code, 'name': subj_name, 'current_gp': curr_gp, 'credit': credit,
                    'max_potential_gp': 4.0, 'source': source
                })
                if improvement_target_gp is not None:
                    simulated_gp = max(curr_gp, improvement_target_gp)
                    projected_points_all += (simulated_gp - curr_gp) * credit

    proj_cgpa_retakes = projected_points_retakes / total_credits if total_credits > 0 else 0.0
    proj_cgpa_all = projected_points_all / total_credits if total_credits > 0 else 0.0

    improvement_candidates.sort(key=lambda x: x['code'])
    already_attempted.sort(key=lambda x: x['code'])
    ineligible_retake_cleared.sort(key=lambda x: x['code'])

    return {
        "current_true_cgpa": deep_result['true_cgpa'],
        "projected_cgpa_after_retakes": round(proj_cgpa_retakes, 2),
        "projected_cgpa_after_all": round(proj_cgpa_all, 2),
        "cgpa_gain_from_retakes": round(proj_cgpa_retakes - deep_result['true_cgpa'], 2),
        "cgpa_gain_from_improvements": round(proj_cgpa_all - proj_cgpa_retakes, 2),
        "retake_clear_gp": retake_clear_gp,
        "improvement_target_gp": improvement_target_gp,
        "pending_retakes": pending_retakes,
        "improvement_candidates": improvement_candidates,
        "already_attempted": already_attempted,
        "ineligible_retake_cleared": ineligible_retake_cleared,
    }


def compute_adjusted_cgpa(
    effective_grades: dict,
    overrides: dict,
) -> tuple[float, float]:
    """
    Recompute CGPA after applying per-subject GP overrides.
    Returns (adjusted_cgpa, total_credits).
    Override only applies if target_gp > current_gp (R3: result stays unless better).
    """
    total_points = 0.0
    total_credits = 0.0
    for code, g in effective_grades.items():
        credit = g['credit']
        gp = g['gp']
        if code in overrides:
            target = overrides[code]
            if target > gp:  # only replace if strictly better
                gp = target
        total_points += gp * credit
        total_credits += credit
    adjusted_cgpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0
    return adjusted_cgpa, total_credits


# ---------------------------------------------------------------------------
# Readd / Incomplete History Resolution
# ---------------------------------------------------------------------------

def get_incomplete_history_students(profile_name: str) -> list:
    """
    Detects students whose exam result count is less than the number of
    exam scans in this profile's scan_log.

    A student with fewer results than the profile's exam count is likely a
    readd student whose earlier semesters (from a previous batch) were never
    scanned into this profile.

    Returns list of dicts: {reg_no, name, sess_id, student_exam_count, profile_exam_count}
    """
    with get_connection() as conn:
        profile_exam_count = conn.execute(
            "SELECT COUNT(*) FROM scan_log WHERE profile_name=?",
            (profile_name,)
        ).fetchone()[0]

        if profile_exam_count == 0:
            return []

        cur = conn.execute("""
            SELECT s.reg_no, s.name, s.sess_id,
                   COUNT(DISTINCT er.exam_id) as student_exam_count
            FROM students s
            LEFT JOIN exam_results er
                   ON s.profile_name = er.profile_name
                  AND s.reg_no = er.reg_no
                  AND s.sess_id = er.sess_id
            WHERE s.profile_name=?
            GROUP BY s.reg_no, s.sess_id
            HAVING COUNT(DISTINCT er.exam_id) < ?
            ORDER BY student_exam_count ASC
        """, (profile_name, profile_exam_count))

        results = []
        for row in cur.fetchall():
            results.append({
                "reg_no":               row[0],
                "name":                 row[1],
                "sess_id":              row[2],
                "student_exam_count":   row[3],
                "profile_exam_count":   profile_exam_count,
            })
        return results


def save_cross_batch_history(
    profile_name: str,
    reg_no: int,
    scanned_history: list,
    exam_name_map: dict,
    sess_id: str = None
) -> int:
    """
    Saves intelligently filtered cross-batch history for a readd student.

    Process:
    1. Attaches exam names from exam_name_map and filters out retake/improvement exams.
    2. Groups remaining (main) exams by their semester label
       (e.g. "1st year 1st Semester") extracted from the exam name.
    3. For each semester group, keeps only the result with the highest numeric exam_id
       ('latest exam wins' — handles students who repeated a semester due to readd).
    4. Saves the winning results under (profile_name, reg_no) via the standard upsert
       pipeline, so the existing CGPA calculation works automatically.

    Returns the number of semester results saved.
    """
    RETAKE_KEYWORDS = [
        "retake", "re-take", "improvement", "special",
        "make-up", "makeup", "supplementary"
    ]
    # Matches patterns like "1st year 1st Semester", "2nd year 2nd Semester", etc.
    SEM_PATTERN = re.compile(
        r'(\d+(?:st|nd|rd|th)\s+year\s+\d+(?:st|nd|rd|th)\s+semester)',
        re.IGNORECASE
    )

    # Step 1: Attach resolved exam names and filter retake/improvement exams
    main_exams = []
    for res in scanned_history:
        eid = str(res.get('_exam_id', ''))
        ename = exam_name_map.get(eid, res.get('_exam_name', ''))
        if not ename:
            continue
        if any(kw in ename.lower() for kw in RETAKE_KEYWORDS):
            continue
        # Work on a copy to avoid mutating the caller's data
        r = dict(res)
        r['_resolved_exam_name'] = ename
        r['_exam_id'] = eid
        main_exams.append(r)

    if not main_exams:
        return 0

    # Resolve sess_id: use provided value, or look up from students table
    if not sess_id:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT sess_id FROM students WHERE profile_name=? AND reg_no=? LIMIT 1",
                (profile_name, reg_no)
            ).fetchone()
            sess_id = row[0] if row else 'AUTO'

    # Step 2: Group by semester label, keep latest exam_id per group
    semester_groups = {}  # sem_label -> (exam_id_int, result_dict)
    for res in main_exams:
        ename = res['_resolved_exam_name']
        m = SEM_PATTERN.search(ename)
        sem_label = m.group(1).lower().strip() if m else ename.lower()

        try:
            eid_int = int(res['_exam_id'])
        except (ValueError, TypeError):
            eid_int = 0

        if sem_label not in semester_groups:
            semester_groups[sem_label] = (eid_int, res)
        else:
            current_eid, _ = semester_groups[sem_label]
            if eid_int > current_eid:
                semester_groups[sem_label] = (eid_int, res)

    # Step 3: Save each winning semester result under the current profile
    stmts = []
    for sem_label, (eid_int, res) in semester_groups.items():
        exam_id  = str(res['_exam_id'])
        exam_name = res['_resolved_exam_name']
        upsert_exam_result(profile_name, res, exam_id, exam_name, stmts, sess_id=sess_id)

    if stmts:
        with get_connection() as conn:
            for sql, params in stmts:
                conn.execute(sql, params)

    logger.info(
        f"save_cross_batch_history: saved {len(semester_groups)} semester(s) "
        f"for reg_no={reg_no} under profile='{profile_name}'"
    )
    return len(semester_groups)


def delete_exam(profile_name: str, exam_id: str):

    """
    Permanently deletes all data for a specific exam scan.
    Student roster is preserved — only exam_results, subject_grades,
    and scan_log rows for this (profile_name, exam_id) are removed.
    Safe to call multiple times (idempotent).
    """
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM subject_grades WHERE profile_name=? AND exam_id=?",
            (profile_name, exam_id)
        )
        conn.execute(
            "DELETE FROM exam_results WHERE profile_name=? AND exam_id=?",
            (profile_name, exam_id)
        )
        conn.execute(
            "DELETE FROM scan_log WHERE profile_name=? AND exam_id=?",
            (profile_name, exam_id)
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Readd Detection Helpers
# ---------------------------------------------------------------------------

def get_senior_batch_profiles(profile_name: str) -> dict:
    """
    Given a profile like 'cse 10', returns all profiles with the same
    department prefix but a LOWER batch number (i.e. senior/older batches).
    Example: 'cse 10' → returns {'cse 09': {...}, 'cse 08': {...}, ...}
    """
    parts = profile_name.lower().split()
    if len(parts) < 2:
        return {}
    dept_prefix = parts[0]
    try:
        batch_num = int(parts[1])
    except ValueError:
        return {}

    all_profiles = get_profiles()
    senior = {}
    for p_name, p_data in all_profiles.items():
        p_parts = p_name.lower().split()
        if len(p_parts) >= 2 and p_parts[0] == dept_prefix:
            try:
                p_batch = int(p_parts[1])
                if p_batch < batch_num:
                    senior[p_name] = p_data
            except ValueError:
                continue
    return senior


def get_profile_student_regs(profile_name: str) -> set:
    """Returns the set of registration numbers currently in a profile."""
    regs = set()
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT reg_no FROM students WHERE profile_name=?", (profile_name,)
        )
        for row in cur.fetchall():
            regs.add(int(row[0]))
    return regs


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def delete_profile(profile_name: str):
    with get_connection() as conn:
        # Manually cascade since WAL mode may buffer
        conn.execute("DELETE FROM exam_results WHERE profile_name=?", (profile_name,))
        conn.execute("DELETE FROM subject_grades WHERE profile_name=?", (profile_name,))
        conn.execute("DELETE FROM students WHERE profile_name=?", (profile_name,))
        conn.execute("DELETE FROM profiles WHERE name=?", (profile_name,))
        conn.execute("DELETE FROM scan_log WHERE profile_name=?", (profile_name,))
        conn.commit()


def rename_profile(old_name: str, new_name: str):
    with get_connection() as conn:
        # Insert new profile by copying old
        conn.execute("""
            INSERT INTO profiles (name, pro_id, sess_id, timestamp)
            SELECT ?, pro_id, sess_id, timestamp FROM profiles WHERE name=?
        """, (new_name, old_name))
        
        # Move all children to new profile
        conn.execute("UPDATE students SET profile_name=? WHERE profile_name=?", (new_name, old_name))
        conn.execute("UPDATE exam_results SET profile_name=? WHERE profile_name=?", (new_name, old_name))
        conn.execute("UPDATE subject_grades SET profile_name=? WHERE profile_name=?", (new_name, old_name))
        conn.execute("UPDATE scan_log SET profile_name=? WHERE profile_name=?", (new_name, old_name))
        
        # Delete old profile
        conn.execute("DELETE FROM profiles WHERE name=?", (old_name,))
        conn.commit()


# ---------------------------------------------------------------------------
# Advanced Analytics (Trends & Grade Distribution)
# ---------------------------------------------------------------------------

def get_longitudinal_data(profile_name: str) -> dict:
    """
    Retrieves longitudinal data for all students in a profile, filtering out
    retake exams and ensuring "latest exam_id wins" for readmitted students.
    Returns: dict mapping reg_no -> list of semester records (sorted by semester_num)
    """
    import re
    RETAKE_KEYWORDS = [
        "retake", "re-take", "improvement", "special",
        "make-up", "makeup", "supplementary"
    ]
    SEM_PATTERN = re.compile(
        r'(\d+(?:st|nd|rd|th)\s+year\s+\d+(?:st|nd|rd|th)\s+semester)',
        re.IGNORECASE
    )

    with get_connection() as conn:
        # Fetch all exams and students for this profile
        cur = conn.execute("""
            SELECT e.reg_no, s.name, e.exam_id, e.exam_name, e.sgpa, e.cgpa, e.result_status
            FROM exam_results e
            JOIN students s ON e.profile_name = s.profile_name
                           AND e.reg_no = s.reg_no
                           AND e.sess_id = s.sess_id
            WHERE e.profile_name = ?
        """, (profile_name,))
        
        all_records = cur.fetchall()

    student_groups = {} # reg_no -> {sem_label -> record_dict}

    for row in all_records:
        reg_no, name, exam_id, exam_name, sgpa, cgpa, result_status = row
        
        # Safeguard: if exam_name is NaN (float) or int, force to string
        safe_exam_name = str(exam_name) if exam_name is not None and exam_name == exam_name else ""
        
        if any(kw in safe_exam_name.lower() for kw in RETAKE_KEYWORDS):
            continue
            
        m = SEM_PATTERN.search(safe_exam_name)
        sem_label = m.group(1).title().strip() if m else safe_exam_name.title().strip()
        
        try:
            eid_int = int(exam_id)
        except (ValueError, TypeError):
            eid_int = 0

        # Attempt to parse semester num from label
        sem_num = 0
        yr_match = re.search(r'(\d)[a-z]{2}\s*Yr', sem_label, re.IGNORECASE)
        sem_match = re.search(r'(\d)[a-z]{2}\s*Sem', sem_label, re.IGNORECASE)
        # Fallback to older patterns if 'Yr' isn't used
        if not yr_match:
            yr_match = re.search(r'(\d)[a-z]{2}\s*Year', sem_label, re.IGNORECASE)
        if not sem_match:
            sem_match = re.search(r'(\d)[a-z]{2}\s*Semester', sem_label, re.IGNORECASE)
            
        if yr_match and sem_match:
            yr = int(yr_match.group(1))
            sem_in_yr = int(sem_match.group(1))
            sem_num = (yr - 1) * 2 + sem_in_yr

        rec = {
            'reg_no': reg_no,
            'name': name,
            'exam_id': eid_int,
            'exam_name': exam_name,
            'sgpa': sgpa or 0.0,
            'cgpa': cgpa or 0.0,
            'result_status': result_status,
            'semester_num': sem_num,
            'semester_label': sem_label
        }

        if reg_no not in student_groups:
            student_groups[reg_no] = {}
        
        # Latest exam_id wins for the same semester label
        if sem_label not in student_groups[reg_no]:
            student_groups[reg_no][sem_label] = rec
        else:
            if eid_int > student_groups[reg_no][sem_label]['exam_id']:
                student_groups[reg_no][sem_label] = rec

    # Convert to sorted list per student
    final_data = {}
    for reg_no, sem_dict in student_groups.items():
        if not sem_dict:
            continue
        sorted_records = sorted(sem_dict.values(), key=lambda x: (x['semester_num'], x['exam_id']))
        final_data[reg_no] = sorted_records

    return final_data


def get_retake_success_stats(profile_name: str) -> list[dict]:
    """
    Computes success rates for retakes and improvements across the batch.
    Requires at least 2 attempts for a subject.
    """
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT reg_no, subject_code, MIN(grade_point) as first_gp, MAX(grade_point) as best_gp, COUNT(*) as attempts
            FROM subject_grades
            WHERE profile_name = ?
            GROUP BY reg_no, subject_code
            HAVING COUNT(*) > 1
        """, (profile_name,))
        
        rows = cur.fetchall()

    stats = []
    for reg, code, first_gp, best_gp, attempts in rows:
        passed_after = (first_gp < 2.0 and best_gp >= 2.0)
        gp_gain = best_gp - first_gp
        stats.append({
            'reg_no': reg,
            'subject_code': code,
            'attempts': attempts,
            'first_gp': first_gp,
            'best_gp': best_gp,
            'gp_gain': gp_gain,
            'passed_after_retake': passed_after
        })
    return stats


def get_cross_batch_comparison(profile_names: list[str], semester_pattern: str) -> dict:
    """
    Compares the performance of multiple batches on a specific semester.
    Finds the main exam (highest student count) matching the pattern for each profile.
    """
    RETAKE_KEYWORDS = [
        "retake", "re-take", "improvement", "special",
        "make-up", "makeup", "supplementary"
    ]
    
    results = {}
    
    with get_connection() as conn:
        for profile in profile_names:
            # Find all exams matching the pattern
            cur = conn.execute("""
                SELECT exam_id, exam_name, COUNT(reg_no) as student_count
                FROM exam_results
                WHERE profile_name = ? AND exam_name LIKE ?
                GROUP BY exam_id, exam_name
            """, (profile, f"%{semester_pattern}%"))
            
            exams = cur.fetchall()
            
            # Filter out retakes and find the one with the most students (the "main" cohort)
            main_exam = None
            max_students = 0
            
            for eid, ename, scount in exams:
                if any(kw in (ename or '').lower() for kw in RETAKE_KEYWORDS):
                    continue
                # If tied, take higher exam_id
                if scount > max_students or (scount == max_students and main_exam and int(eid) > int(main_exam[0])):
                    max_students = scount
                    main_exam = (eid, ename)
            
            if not main_exam:
                continue
                
            eid, ename = main_exam
            
            # Fetch all SGPAs for this exam
            cur = conn.execute("""
                SELECT sgpa
                FROM exam_results
                WHERE profile_name = ? AND exam_id = ?
            """, (profile, eid))
            
            sgpas = [row[0] for row in cur.fetchall() if row[0] is not None]
            
            if not sgpas:
                continue
                
            import statistics
            sgpas_sorted = sorted(sgpas)
            
            results[profile] = {
                'exam_name': ename,
                'students': len(sgpas),
                'mean_sgpa': round(statistics.mean(sgpas), 2),
                'median_sgpa': round(statistics.median(sgpas), 2),
                'pass_rate': round(sum(1 for s in sgpas if s >= 2.0) / len(sgpas) * 100, 1),
                'honours_count': sum(1 for s in sgpas if s >= 3.75),
                'sgpa_list': sgpas
            }
            
    return results


# ---------------------------------------------------------------------------
# Legacy migration helpers
# ---------------------------------------------------------------------------

def migrate_legacy_json():
    """One-time migration from saved_profiles.json → SQLite. Runs only if DB is empty."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_profiles.json")
    if not os.path.exists(json_path):
        return

    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    if count > 0:
        return  # Already migrated

    logger.info("Migrating legacy profiles from JSON...")
    try:
        with open(json_path, "r") as f:
            legacy = json.load(f)

        for name, data in legacy.items():
            pro_id = str(data.get('pro_id', ''))
            sess_id = str(data.get('sess_id', ''))
            ts = data.get('timestamp', time.time())

            if not sess_id and data.get('regs'):
                first = data['regs'][0]
                if isinstance(first, list) and len(first) > 1:
                    sess_id = str(first[1])

            with get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)",
                    (name, pro_id, sess_id, ts)
                )
                conn.commit()

            for r_item in data.get('regs', []):
                if isinstance(r_item, list):
                    r_no = int(r_item[0])
                    s_id = str(r_item[1]) if len(r_item) > 1 else sess_id
                    s_name = str(r_item[2]) if len(r_item) > 2 else 'Unknown'
                else:
                    r_no = int(r_item)
                    s_id = sess_id
                    s_name = 'Unknown'
                upsert_student(name, r_no, s_name, s_id)

        os.rename(json_path, json_path + ".backup")
        logger.info("Legacy JSON migration complete.")
    except Exception as e:
        logger.error("Legacy migration failed: %s", e)

# ---------------------------------------------------------------------------
# Cache Helpers
# ---------------------------------------------------------------------------

def get_meta_cache(key: str, ttl_seconds: int = 86400) -> dict | None:
    """Returns cached JSON value if within TTL, else None."""
    with get_connection() as conn:
        try:
            row = conn.execute(
                "SELECT value, cached_at FROM meta_cache WHERE key=?", (key,)
            ).fetchone()
            if row and (time.time() - row[1]) < ttl_seconds:
                return json.loads(row[0])
        except sqlite3.OperationalError:
            pass # Table might not be created yet during first boot
    return None

def set_meta_cache(key: str, value: dict):
    """Stores a JSON-serializable value in the persistent cache."""
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO meta_cache (key, value, cached_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time())
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass # Table might not be created yet

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
_bootstrapped = False

def _bootstrap():
    global _bootstrapped
    if _bootstrapped:
        return
    init_db()
    migrate_schema_v2()
    migrate_schema_v3()
    migrate_schema_v4()
    migrate_legacy_json()
    _bootstrapped = True

_bootstrap()
