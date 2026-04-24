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

# Optional: Turso (libSQL) support for cloud persistence
try:
    import libsql_client
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False

logger = logging.getLogger(__name__)

# --- Database Configuration ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_finder.db")
CREDIT_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credit_mapping.json")

# Compatibility Wrapper for libsql-client to match sqlite3 API
class LibsqlConnectionWrapper:
    def __init__(self, client):
        self.client = client
    
    def execute(self, sql, params=None):
        res = self.client.execute(sql, params or [])
        return LibsqlResultWrapper(res)
    
    def executescript(self, sql):
        # libsql-client doesn't have executescript, so we split by ';'
        # This is for internal migration use; app doesn't use it much.
        for stmt in sql.split(';'):
            if stmt.strip():
                self.client.execute(stmt)
                
    def batch(self, statement_list):
        # statement_list is a list of (sql, params) or sql strings
        return self.client.batch(statement_list)

    def commit(self):
        pass # libsql-client executes are atomic and auto-commit
        
    def close(self):
        self.client.close()
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        
    def cursor(self):
        return self # The client itself handles execution in this wrapper
    
    # Map common cursor methods to the client or result set
    def fetchall(self):
        # Note: This is a bit tricky since client.execute returns the result.
        # Most of our app uses 'conn.execute(sql).fetchall()'
        # We handle this by making execute() return a wrapper for the result.
        pass

class LibsqlResultWrapper:
    def __init__(self, result_set):
        self.result_set = result_set
        self.rows = result_set.rows
        self.columns = result_set.columns
        self._index = 0
        
    @property
    def description(self):
        # sqlite3 description is a tuple of (name, None, None, None, None, None, None)
        return tuple((col, None, None, None, None, None, None) for col in self.columns)

    @property
    def rowcount(self):
        return getattr(self.result_set, 'rows_affected', -1)

    @property
    def lastrowid(self):
        return getattr(self.result_set, 'last_insert_rowid', None)

    def __iter__(self):
        return iter(self.rows)
        
    def fetchall(self):
        return self.rows
        
    def fetchone(self):
        if self._index < len(self.rows):
            res = self.rows[self._index]
            self._index += 1
            return res
        return None

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


def is_using_turso() -> bool:
    """Turso Cloud Mode deactivated per user request."""
    return False


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
                GROUP BY profile_name, reg_no, exam_id
            )
        """)

        # --- De-duplicate legacy students rows ---
        cur.execute("""
            DELETE FROM students
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM students
                GROUP BY profile_name, reg_no
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


def upsert_subject_grades(profile_name: str, reg_no: int, exam_id: str, subjects: list, exam_name: str = None, statement_list: list = None):
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

    sql = """
        INSERT OR REPLACE INTO subject_grades
        (profile_name, reg_no, exam_id, subject_code, subject_name, grade_point, credit_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    
    for s in subjects:
        code = str(s.get('code', '')).strip().upper().replace(' ', '-')
        if not code: continue
        subj_name = str(s.get('name', '')).strip()
        gp = _parse_gp(s.get('gp', 0))
        ch = get_subject_credits(code, profile_name, exam_name)
        params = (profile_name, reg_no, exam_id, code, subj_name, gp, ch)
        
        if statement_list is not None:
            statement_list.append((sql, params))
        else:
            with get_connection() as conn:
                conn.execute(sql, params)


def upsert_exam_result(profile_name: str, res: dict, exam_id: str, exam_name: str, statement_list: list = None):
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

    sql = """
        INSERT OR REPLACE INTO exam_results
            (profile_name, reg_no, exam_id, exam_name, result_status, sgpa, cgpa, portal_sgpa, portal_cgpa, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (profile_name, reg_no, exam_id, exam_name, status, sgpa, cgpa, portal_sgpa, portal_cgpa, json.dumps(res))

    if statement_list is not None:
        statement_list.append((sql, params))
    else:
        with get_connection() as conn:
            conn.execute(sql, params)

    # Now upsert subject grades
    upsert_subject_grades(profile_name, reg_no, exam_id, subjects, exam_name, statement_list)


def upsert_student(profile_name: str, reg_no: int, name: str, sess_id: str, statement_list: list = None):
    """Idempotent student upsert — updates name if reg already exists."""
    sql = """
        INSERT INTO students (profile_name, reg_no, name, sess_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(profile_name, reg_no) DO UPDATE SET name=excluded.name, sess_id=excluded.sess_id
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


def get_scan_log() -> list:
    """Return all scan_log rows as list of dicts."""
    with get_connection() as conn:
        cur = conn.execute("SELECT profile_name, exam_id, scanned_at, student_count FROM scan_log")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


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
        upsert_exam_result(profile_name, res, exam_id, exam_name, stmts)

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
        upsert_exam_result(profile_name, res, exam_id, exam_name, stmts)
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


def remove_student_from_profile(profile_name: str, reg_no: int):
    """Removes a student and all their associated results from a profile."""
    with get_connection() as conn:
        conn.execute("DELETE FROM subject_grades WHERE profile_name=? AND reg_no=?", (profile_name, reg_no))
        conn.execute("DELETE FROM exam_results WHERE profile_name=? AND reg_no=?", (profile_name, reg_no))
        conn.execute("DELETE FROM students WHERE profile_name=? AND reg_no=?", (profile_name, reg_no))
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
            "SELECT reg_no, name FROM students WHERE profile_name=?", (profile_name,)
        )
        students = students_cur.fetchall()

        for reg_no, name in students:
            # Get best grade per subject across all exams for this student
            best_cur = conn.execute("""
                SELECT subject_code, MAX(grade_point) as best_gp, credit_hours
                FROM subject_grades
                WHERE profile_name=? AND reg_no=?
                GROUP BY subject_code
            """, (profile_name, reg_no))
            best_grades = best_cur.fetchall()

            if not best_grades:
                continue

            # Weighted GPA: sum(gp * ch) / sum(ch)
            total_points = sum(row[1] * row[2] for row in best_grades)
            total_credits = sum(row[2] for row in best_grades)
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
                WHERE profile_name=? AND reg_no=? AND grade_point < 2.0
            """, (profile_name, reg_no))
            has_ever_failed = fail_check_cur.fetchone()[0] > 0

            # Latest raw CGPA from exam_results for comparison
            raw_cur = conn.execute("""
                SELECT cgpa, result_status FROM exam_results
                WHERE profile_name=? AND reg_no=?
                ORDER BY exam_id DESC LIMIT 1
            """, (profile_name, reg_no))
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


def get_all_subject_data(profile_name: str) -> list:
    """
    Returns a flat list of all subjects and their best grades for every student.
    Useful for DataFrame-based analysis (heatmaps, boxplots, clustering).
    """
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT sg.reg_no, s.name, sg.subject_code, sg.subject_name, MAX(sg.grade_point) as gp, sg.credit_hours
            FROM subject_grades sg
            JOIN students s ON sg.profile_name = s.profile_name AND sg.reg_no = s.reg_no
            WHERE sg.profile_name=?
            GROUP BY sg.reg_no, sg.subject_code
        """, (profile_name,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


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
            SELECT s.reg_no, s.name, er.sgpa, er.cgpa, er.result_status, er.raw_json
            FROM students s
            JOIN exam_results er ON s.profile_name = er.profile_name AND s.reg_no = er.reg_no
            WHERE s.profile_name=? AND er.exam_id=?
        """, (profile_name, exam_id))
        students = students_cur.fetchall()

        for reg_no, name, sgpa_col, cgpa, db_status, raw_json_str in students:
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
            JOIN students s ON sg.profile_name = s.profile_name AND sg.reg_no = s.reg_no
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
    Sums all credits from credit_mapping.json for subjects belonging to
    a given semester number (1–8) in the specified department.
    """
    dept_map = _credit_map.get(dept, {})
    total = 0.0
    for code, credits in dept_map.items():
        if get_semester_from_code(code, dept) == semester_num:
            # Fix: CSE 2nd semester strictly has Physics, no Chemistry. 
            # So exclude CHE to prevent over-counting the target semester credits.
            if dept == 'CSE' and semester_num == 2 and code.startswith('CHE-'):
                continue
            total += credits
    return total


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
                'exam_id': eid_int
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
                # Only apply if retake grade is strictly better
                if gp > effective_grades[code]['gp']:
                    effective_grades[code]['gp'] = gp
                    effective_grades[code]['source'] = 'retake_improved'
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
    }


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
                   ON s.profile_name = er.profile_name AND s.reg_no = er.reg_no
            WHERE s.profile_name=?
            GROUP BY s.reg_no
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
    exam_name_map: dict
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
        upsert_exam_result(profile_name, res, exam_id, exam_name, stmts)

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
# Bootstrap
# ---------------------------------------------------------------------------
init_db()
migrate_schema_v2()
migrate_schema_v3()
migrate_legacy_json()
