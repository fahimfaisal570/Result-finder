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

logger = logging.getLogger(__name__)

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

def get_subject_credits(subject_code: str, profile_name: str) -> float:
    """Lookup credits from the nested PDF mapping, default to 3.0."""
    code = str(subject_code).strip().upper().replace(' ', '-')
    dept = get_dept_from_profile(profile_name)
    
    # Check the specific department bucket first
    dept_map = _credit_map.get(dept, {})
    if code in dept_map:
        return dept_map[code]
    
    # Fallback: check other departments just in case it's a shared GED/MATH code not caught in dept syllabus
    for d in _credit_map.values():
        if code in d:
            return d[code]
            
    return 3.0
def get_connection() -> sqlite3.Connection:
    """Return a new connection. Caller is responsible for context management."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # Safe for concurrent reads
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


# ---------------------------------------------------------------------------
# Core Upsert Helpers (idempotent — safe to call multiple times)
# ---------------------------------------------------------------------------

def _parse_gp(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def upsert_subject_grades(profile_name: str, reg_no: int, exam_id: str, subjects: list):
    """
    Insert or replace individual subject grades.
    Includes 'Syllabus-Aware' failure inference: If a subject is in the 
    department's syllabus but missing from the scrape, it's logged as a fail (0.0).
    """
    scraped_codes = {str(s.get('code', '')).strip().upper().replace(' ', '-') for s in subjects if s.get('code')}
    dept = get_dept_from_profile(profile_name)
    dept_map = _credit_map.get(dept, {})
    
    # 1. Identify "Hidden Failures" (In syllabus but not in scrape)
    # We only do this if the scrape actually found SOME subjects (sanity check)
    if len(subjects) >= 2:
        # Determine the year/semester levels found in the scrape (e.g. 'EEE-22', 'MATH-22')
        # We take the code prefix + the first two digits to identify the level
        scraped_levels = set()
        for c in scraped_codes:
            # Matches 'EEE-22' out of 'EEE-2201'
            m = re.match(r'^([A-Z]{2,6}[\-\s]*\d{2})', c, re.I)
            if m: scraped_levels.add(m.group(1).upper())
            
        for code, credit in dept_map.items():
            # Matches 'EEE-22' out of 'EEE-2201'
            m = re.match(r'^([A-Z]{2,6}[\-\s]*\d{2})', code, re.I)
            level = m.group(1).upper() if m else None
            
            if level in scraped_levels and code not in scraped_codes:
                # This is likely a failed/missing subject for THIS semester
                subjects.append({
                    'code': code,
                    'name': 'Hidden Failure (Auto-Inferred)',
                    'grade': 'F',
                    'gp': 0.0,
                    'is_inferred': True
                })

    with get_connection() as conn:
        for s in subjects:
            code = str(s.get('code', '')).strip()
            if not code:
                continue
            subj_name = str(s.get('name', '')).strip()
            gp = _parse_gp(s.get('gp', 0))
            
            # Use PDF credit mapping if available, otherwise fallback to 3.0
            ch = get_subject_credits(code, profile_name)
            
            conn.execute("""
                INSERT OR REPLACE INTO subject_grades
                    (profile_name, reg_no, exam_id, subject_code, subject_name, grade_point, credit_hours)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (profile_name, reg_no, exam_id, code, subj_name, gp, ch))
        conn.commit()


def upsert_exam_result(profile_name: str, res: dict, exam_id: str, exam_name: str):
    """
    Idempotent upsert of one student's exam result.
    Also extracts and stores subject-level grades.
    """
    reg_no = int(res.get('Registration No', res.get('Reg', 0)))
    sgpa = _parse_gp(res.get('GPA', res.get('SGPA', 0)))
    cgpa = _parse_gp(res.get('CGPA', 0))
    status = str(res.get('Result', res.get('Overall Result', 'Unknown')))

    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO exam_results
                (profile_name, reg_no, exam_id, exam_name, result_status, sgpa, cgpa, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (profile_name, reg_no, exam_id, exam_name, status, sgpa, cgpa, json.dumps(res)))
        conn.commit()

    # Now upsert subject grades from raw_json
    subjects = res.get('Subjects', [])
    upsert_subject_grades(profile_name, reg_no, exam_id, subjects)


def upsert_student(profile_name: str, reg_no: int, name: str, sess_id: str):
    """Idempotent student upsert — updates name if reg already exists."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO students (profile_name, reg_no, name, sess_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(profile_name, reg_no) DO UPDATE SET name=excluded.name, sess_id=excluded.sess_id
        """, (profile_name, reg_no, name, sess_id))
        conn.commit()


def update_scan_log(profile_name: str, exam_id: str, student_count: int):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO scan_log (profile_name, exam_id, scanned_at, student_count)
            VALUES (?, ?, ?, ?)
        """, (profile_name, exam_id, time.time(), student_count))
        conn.commit()


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


# ---------------------------------------------------------------------------
# High-level save functions
# ---------------------------------------------------------------------------

def save_profile_and_results(profile_name: str, pro_id: str, sess_id: str,
                              results_list: list, exam_id: str, exam_name: str):
    """
    Saves a newly scraped batch as a new profile.
    Idempotent — safe to call multiple times; students are upserted.
    """
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp)
            VALUES (?, ?, ?, ?)
        """, (profile_name, pro_id, sess_id, time.time()))
        conn.commit()

    for res in results_list:
        reg_no = int(res.get('Registration No', res.get('Reg', 0)))
        student_name = str(res.get('Name', res.get('Student Name', 'Unknown')))
        student_sess = str(res.get('_sess_id', sess_id))
        upsert_student(profile_name, reg_no, student_name, student_sess)
        upsert_exam_result(profile_name, res, exam_id, exam_name)

    update_scan_log(profile_name, exam_id, len(results_list))
    return True


def save_exam_analytics_only(profile_name: str, exam_id: str, exam_name: str, results_list: list):
    """
    Saves ONLY exam results (and subject grades) for an existing profile.
    Does NOT touch the profile row or students list.
    """
    for res in results_list:
        upsert_exam_result(profile_name, res, exam_id, exam_name)
    update_scan_log(profile_name, exam_id, len(results_list))
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
            if sgpa == 0.0 and raw_json_str:
                try:
                    raw = json.loads(raw_json_str)
                    sgpa = _parse_gp(raw.get('GPA', raw.get('SGPA', 0)) or 0)
                except Exception:
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
migrate_legacy_json()
