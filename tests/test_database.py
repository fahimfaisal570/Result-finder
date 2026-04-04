"""
tests/test_database.py
Unit tests for database.py — ACID properties, idempotency, retake-aware CGPA.
Uses a temporary in-memory DB via monkeypatching DB_PATH.
"""
import os, sys, json, tempfile, unittest, time

# Point to project root so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Redirect DB to a temp file so tests never touch production data
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
TEST_DB = _tmp.name

import database
# Monkey-patch DB path BEFORE any tables are created
database.DB_PATH = TEST_DB
# Re-run bootstrap so tables exist in the test DB
database.init_db()
database.migrate_schema_v2()

PROFILE = "test_profile"
PRO_ID  = "99"
SESS_ID = "42"
EXAM_ID = "1001"
EXAM_NM = "Test Exam Semester 1"

def make_result(reg, name="Test Student", cgpa=3.5, gpa=3.8, subjects=None):
    if subjects is None:
        subjects = [
            {"code": "CS101", "name": "Intro CS", "grade": "A", "gp": "4.00"},
            {"code": "MA101", "name": "Math",     "grade": "B", "gp": "3.00"},
        ]
    return {
        "Registration No": reg,
        "Name": name,
        "CGPA": str(cgpa),
        "GPA":  str(gpa),
        "Result": "Promoted",
        "_sess_id": SESS_ID,
        "_exam_id": EXAM_ID,
        "Subjects": subjects,
    }


class TestSchemaAndAcid(unittest.TestCase):

    def setUp(self):
        """Wipe tables before each test — children first to respect FK constraints."""
        with database.get_connection() as conn:
            conn.executescript("""
                DELETE FROM subject_grades;
                DELETE FROM exam_results;
                DELETE FROM scan_log;
                DELETE FROM students;
                DELETE FROM profiles;
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # 1. Profile creation
    # ------------------------------------------------------------------
    def test_save_profile_creates_profile_row(self):
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID,
                                          [make_result(1001)], EXAM_ID, EXAM_NM)
        profiles = database.get_profiles()
        self.assertIn(PROFILE, profiles)
        self.assertEqual(profiles[PROFILE]["pro_id"], PRO_ID)

    # ------------------------------------------------------------------
    # 2. No duplicate exam_results (ACID: insert idempotency)
    # ------------------------------------------------------------------
    def test_no_duplicate_exam_results_on_double_save(self):
        res = [make_result(1001), make_result(1002)]
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID, res, EXAM_ID, EXAM_NM)
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID, res, EXAM_ID, EXAM_NM)

        with database.get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM exam_results WHERE profile_name=?", (PROFILE,)
            ).fetchone()[0]
        self.assertEqual(count, 2, "Duplicate exam_results rows detected after double save!")

    # ------------------------------------------------------------------
    # 3. No duplicate students
    # ------------------------------------------------------------------
    def test_no_duplicate_students_on_double_upsert(self):
        with database.get_connection() as conn:
            conn.execute("INSERT INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, 0)", (PROFILE, PRO_ID, SESS_ID))
            conn.commit()
            
        database.upsert_student(PROFILE, 1001, "Alice", SESS_ID)
        database.upsert_student(PROFILE, 1001, "Alice Updated", SESS_ID)  # same reg_no

        with database.get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM students WHERE profile_name=? AND reg_no=1001", (PROFILE,)
            ).fetchone()[0]
        self.assertEqual(count, 1)

    # ------------------------------------------------------------------
    # 4. No duplicate subject_grades per (profile, reg, subject, exam)
    # ------------------------------------------------------------------
    def test_no_duplicate_subject_grades(self):
        with database.get_connection() as conn:
            conn.execute("INSERT INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, 0)", (PROFILE, PRO_ID, SESS_ID))
            conn.commit()
            
        subjects = [{"code": "CS101", "name": "Intro CS", "grade": "A", "gp": "4.00"}]
        database.upsert_subject_grades(PROFILE, 1001, EXAM_ID, subjects)
        database.upsert_subject_grades(PROFILE, 1001, EXAM_ID, subjects)  # repeat

        with database.get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM subject_grades WHERE profile_name=? AND reg_no=1001",
                (PROFILE,)
            ).fetchone()[0]
        self.assertEqual(count, 1)

    # ------------------------------------------------------------------
    # 5. Cascade delete
    # ------------------------------------------------------------------
    def test_delete_profile_cascades(self):
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID,
                                          [make_result(1001)], EXAM_ID, EXAM_NM)
        database.delete_profile(PROFILE)

        with database.get_connection() as conn:
            p = conn.execute("SELECT COUNT(*) FROM profiles WHERE name=?", (PROFILE,)).fetchone()[0]
            s = conn.execute("SELECT COUNT(*) FROM students WHERE profile_name=?", (PROFILE,)).fetchone()[0]
            e = conn.execute("SELECT COUNT(*) FROM exam_results WHERE profile_name=?", (PROFILE,)).fetchone()[0]
            sg = conn.execute("SELECT COUNT(*) FROM subject_grades WHERE profile_name=?", (PROFILE,)).fetchone()[0]
        self.assertEqual(p + s + e + sg, 0, "Orphan rows remain after delete!")

    # ------------------------------------------------------------------
    # 6. Rename profile — no orphans
    # ------------------------------------------------------------------
    def test_rename_profile_no_orphans(self):
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID,
                                          [make_result(1001)], EXAM_ID, EXAM_NM)
        database.rename_profile(PROFILE, "renamed_profile")

        with database.get_connection() as conn:
            old_stu = conn.execute(
                "SELECT COUNT(*) FROM students WHERE profile_name=?", (PROFILE,)
            ).fetchone()[0]
            new_stu = conn.execute(
                "SELECT COUNT(*) FROM students WHERE profile_name='renamed_profile'"
            ).fetchone()[0]
        self.assertEqual(old_stu, 0)
        self.assertEqual(new_stu, 1)

    # ------------------------------------------------------------------
    # 7. Retake-aware CGPA: best grade wins
    # ------------------------------------------------------------------
    def test_effective_cgpa_uses_best_grade(self):
        # First: Seed profile + student
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID,
            [make_result(1001, subjects=[
                {"code": "CS101", "name": "Intro CS", "grade": "C", "gp": "2.00"},
                {"code": "MA101", "name": "Math",     "grade": "B", "gp": "3.00"},
            ])], EXAM_ID, EXAM_NM)

        # Retake exam: CS101 improved to A
        RETAKE_ID = "1002"
        database.upsert_exam_result(PROFILE,
            make_result(1001, subjects=[
                {"code": "CS101", "name": "Intro CS", "grade": "A", "gp": "4.00"},
            ], cgpa=3.2, gpa=4.0),
            RETAKE_ID, "Retake Sem 1"
        )

        results = database.get_effective_cgpa_per_student(PROFILE)
        self.assertEqual(len(results), 1)

        student = results[0]
        # Best CS101 = 4.0, MA101 = 3.0 → (4*3 + 3*3)/(3+3) = 3.5
        self.assertAlmostEqual(student["effective_cgpa"], 3.5, places=1)
        # Should have counted 1 improvement (CS101 went from 2 → 4)
        self.assertEqual(student["improvement_count"], 1)

    # ------------------------------------------------------------------
    # 8. Scan log: should_rescan logic
    # ------------------------------------------------------------------
    def test_should_rescan_no_prior_entry(self):
        self.assertTrue(database.should_rescan(PROFILE, EXAM_ID, interval_minutes=30))

    def test_should_rescan_fresh_entry_returns_false(self):
        database.update_scan_log(PROFILE, EXAM_ID, student_count=10)
        self.assertFalse(database.should_rescan(PROFILE, EXAM_ID, interval_minutes=30))

    def test_should_rescan_old_entry_returns_true(self):
        # Plant a scan_log entry that is 2 hours old
        with database.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scan_log (profile_name, exam_id, scanned_at, student_count)
                VALUES (?, ?, ?, 5)
            """, (PROFILE, EXAM_ID, time.time() - 7200))
            conn.commit()
        self.assertTrue(database.should_rescan(PROFILE, EXAM_ID, interval_minutes=30))

    # ------------------------------------------------------------------
    # 9. save_exam_analytics_only does not modify profiles/students
    # ------------------------------------------------------------------
    def test_save_analytics_only_does_not_touch_profile(self):
        # Seed profile
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID,
                                          [make_result(1001)], EXAM_ID, EXAM_NM)

        original_profiles = database.get_profiles()
        original_regs = original_profiles[PROFILE]["regs"]

        # Save analytics only for a NEW exam
        database.save_exam_analytics_only(PROFILE, "9999", "New Exam",
                                          [make_result(1001, cgpa=3.8)])

        updated_profiles = database.get_profiles()
        self.assertEqual(updated_profiles[PROFILE]["regs"], original_regs,
                         "save_analytics_only must not alter the students list!")

        with database.get_connection() as conn:
            new_exam_count = conn.execute(
                "SELECT COUNT(*) FROM exam_results WHERE profile_name=? AND exam_id='9999'",
                (PROFILE,)
            ).fetchone()[0]
        self.assertEqual(new_exam_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
