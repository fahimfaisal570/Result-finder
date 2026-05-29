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
database.migrate_schema_v3()
database.migrate_schema_v4()

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
            RETAKE_ID, "Retake Sem 1",
            sess_id=SESS_ID
        )

        results = database.get_effective_cgpa_per_student(PROFILE)
        self.assertEqual(len(results), 1)

        student = results[0]
        # Best CS101 = 4.0, MA101 = 3.0 → (4*3 + 3*3)/(3+3) = 3.5
        self.assertAlmostEqual(student["effective_cgpa"], 3.5, places=1)
        # Both CS101(4.0) and MA101(3.0) are > 2.75, so 0 subjects are eligible for improvement
        self.assertEqual(student["improvement_count"], 0)

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

    # ------------------------------------------------------------------
    # 10. GPA Projection / get_semester_courses and fail-aware calculations
    # ------------------------------------------------------------------
    def test_get_semester_courses_include_all_electives(self):
        # Test CSE 7th semester with include_all_electives=True
        courses = database.get_semester_courses("CSE", 7, include_all_electives=True)
        self.assertTrue(len(courses) > 10, "Electives were not fetched correctly")
        
        # Check if there are both core and elective courses
        cores = [c for c in courses if not c["is_elective"]]
        electives = [c for c in courses if c["is_elective"]]
        self.assertEqual(len(cores), 6)
        self.assertTrue(len(electives) > 5)
        
        # Test Civil 8th semester with include_all_electives=True
        civil_courses = database.get_semester_courses("Civil", 8, include_all_electives=True)
        self.assertTrue(len(civil_courses) > 10)
        # All should be treated as electives
        all_electives = all(c["is_elective"] for c in civil_courses)
        self.assertTrue(all_electives)

    def test_cgpa_calculation_includes_fail_courses(self):
        # 1 semester in projection, mode is detailed, with 1 course passed and 1 course failed
        inputs = [{
            'semester': 7,
            'mode': 'detailed',
            'gpa': None,
            'course_grades': [
                {'code': 'CSE-4101', 'credit': 3.0, 'gp': 4.0},  # Passed
                {'code': 'CSE-4102', 'credit': 3.0, 'gp': 0.0},  # Failed
            ]
        }]
        
        # Initial: CGPA 3.5, credits 100.0 (total points = 350.0)
        # Projected semester: points = 3.0 * 4.0 + 3.0 * 0.0 = 12.0
        # Credits added = 6.0 (both passed and failed courses counted)
        # Total points = 362.0, total credits = 106.0
        # Expected graduation CGPA = 362.0 / 106.0 = 3.415...
        res = database.compute_graduation_cgpa_from_inputs(
            adj_cgpa=3.5,
            adj_credits=100.0,
            remaining_semester_inputs=inputs,
            dept="CSE"
        )
        self.assertAlmostEqual(res['graduation_cgpa'], 3.42, places=2)
        self.assertEqual(res['total_new_credits'], 6.0)
        self.assertEqual(res['total_new_points'], 12.0)

    def test_get_student_data_for_exam_optimized(self):
        profile = "cse_test_profile"
        # Seed both student data in a single batch to avoid SQLite OR REPLACE cascade delete
        database.save_profile_and_results(profile, PRO_ID, SESS_ID, [
            make_result(1001, name="Alice", cgpa=3.2, gpa=3.5, subjects=[
                {"code": "CSE-1101", "name": "Intro CS", "grade": "C", "gp": "2.00"},
                {"code": "CSE-1102", "name": "Math",     "grade": "B", "gp": "3.00"},
            ]),
            make_result(1002, name="Bob", cgpa=1.5, gpa=1.0, subjects=[
                {"code": "CSE-1101", "name": "Intro CS", "grade": "F", "gp": "0.00"},
            ])
        ], EXAM_ID, EXAM_NM)

        # Get analytics for this exam
        res = database.get_student_data_for_exam(profile, EXAM_ID)
        self.assertEqual(len(res), 2)

        alice = [r for r in res if r["reg_no"] == 1001][0]
        self.assertEqual(alice["name"], "Alice")
        self.assertAlmostEqual(alice["gpa"], 2.6, places=2)
        self.assertAlmostEqual(alice["cgpa"], 3.2, places=2)
        self.assertEqual(alice["improvement_count"], 1) # 2.0 is in range 2.0 <= gp <= 2.75
        self.assertEqual(alice["retake_count"], 0)
        self.assertFalse(alice["first_chance_fail"])

        bob = [r for r in res if r["reg_no"] == 1002][0]
        self.assertEqual(bob["name"], "Bob")
        self.assertEqual(bob["retake_count"], 1)
        self.assertTrue(bob["first_chance_fail"])

    def test_get_cross_batch_comparison_bulk(self):
        # Seed profiles & results for multiple batches
        batch1 = "cse_09"
        batch2 = "cse_10"
        
        # We need to insert profiles first to satisfy FK constraints
        with database.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)", (batch1, PRO_ID, SESS_ID, time.time()))
            conn.execute("INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)", (batch2, PRO_ID, SESS_ID, time.time()))
            conn.commit()
            
        database.save_exam_analytics_only(batch1, "1001", "3rd Yr 1st Sem Main Exam", [
            make_result(1001, gpa=3.5, cgpa=3.4),
            make_result(1002, gpa=3.7, cgpa=3.6),
        ])
        
        database.save_exam_analytics_only(batch2, "1001", "3rd Yr 1st Sem Main Exam", [
            make_result(2001, gpa=2.8, cgpa=2.9),
            make_result(2002, gpa=3.0, cgpa=3.1),
        ])
        
        res = database.get_cross_batch_comparison([batch1, batch2], "3rd Yr 1st Sem")
        self.assertIn(batch1, res)
        self.assertIn(batch2, res)
        
        self.assertEqual(res[batch1]['students'], 2)
        self.assertAlmostEqual(res[batch1]['mean_gpa'], 3.6, places=2)
        
        self.assertEqual(res[batch2]['students'], 2)
        self.assertAlmostEqual(res[batch2]['mean_gpa'], 2.9, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
