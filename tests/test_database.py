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
database.migrate_schema_v5()

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


    # ------------------------------------------------------------------
    # 12. US-009: Civil Engineering consecutive semester parsing
    # ------------------------------------------------------------------
    def test_longitudinal_data_civil_consecutive_semesters(self):
        """
        Civil Engineering uses exam names like '3rd Year 6th Semester Main Exam'.
        When sem_in_yr > 2, sem_num must equal the raw semester number (6), NOT
        the standard (yr-1)*2 + sem_in_yr formula.
        """
        civil_profile = "civil_test_profile"
        with database.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)",
                (civil_profile, "77", "42", time.time())
            )
            conn.commit()

        # Seed exam name that uses consecutive numbering: 3rd Year 6th Semester
        exam_id_consec = "5001"
        exam_name_consec = "3rd Year 6th Semester Main Exam"
        database.save_exam_analytics_only(civil_profile, exam_id_consec, exam_name_consec, [
            make_result(9001, gpa=3.0, cgpa=2.8),
        ])

        # Also seed a standard exam for contrast: 1st Year 2nd Semester
        exam_id_std = "5002"
        exam_name_std = "1st Year 2nd Semester Main Exam"
        database.save_exam_analytics_only(civil_profile, exam_id_std, exam_name_std, [
            make_result(9001, gpa=2.5, cgpa=2.5),
        ])

        # Now seed student properly for the JOIN
        with database.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)",
                (civil_profile, 9001, "Civil Student", SESS_ID)
            )
            conn.commit()

        data = database.get_longitudinal_data(civil_profile)
        self.assertIn(9001, data, "Student 9001 should appear in longitudinal data")

        records = data[9001]
        sem_nums = [r['semester_num'] for r in records]

        # 1st Year 2nd Semester -> sem_num = (1-1)*2 + 2 = 2
        self.assertIn(2, sem_nums, "Standard 1st year 2nd semester must yield sem_num=2")

        # 3rd Year 6th Semester -> sem_num must = 6 (consecutive), NOT (3-1)*2+6=10
        self.assertIn(6, sem_nums,
            "Civil 3rd year 6th semester (consecutive) must yield sem_num=6, not 10")
        self.assertNotIn(10, sem_nums,
            "Consecutive semester numbers must NOT use the (yr-1)*2+sem formula")

    # ------------------------------------------------------------------
    # 13. US-009: Chronological retake success stats via window function
    # ------------------------------------------------------------------
    def test_retake_success_stats_chronological_first_attempt(self):
        """
        get_retake_success_stats() must identify the FIRST attempt by exam_id order,
        not the lowest grade_point. If first attempt failed (gp<2.0) and a later attempt
        passed (gp>=2.0), passed_after_retake must be True.
        If the high-scoring attempt comes first and the retake is lower, passed_after_retake
        must be False.
        """
        retake_profile = "retake_test_profile"
        with database.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)",
                (retake_profile, "88", SESS_ID, time.time())
            )
            conn.execute(
                "INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)",
                (retake_profile, 8001, "Retake Student", SESS_ID)
            )
            conn.commit()

        # First attempt (exam_id=6001): Failed CS101 with gp=0.0
        # Second attempt (exam_id=6002): Passed CS101 with gp=3.0
        with database.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO subject_grades
                (profile_name, reg_no, exam_id, subject_code, grade_point, credit_hours, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (retake_profile, 8001, "6001", "CS101", 0.0, 3.0, SESS_ID))
            conn.execute("""
                INSERT OR REPLACE INTO subject_grades
                (profile_name, reg_no, exam_id, subject_code, grade_point, credit_hours, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (retake_profile, 8001, "6002", "CS101", 3.0, 3.0, SESS_ID))
            conn.commit()

        stats = database.get_retake_success_stats(retake_profile)
        self.assertEqual(len(stats), 1, "Should have exactly 1 retake record for CS101")

        s = stats[0]
        self.assertEqual(s['reg_no'], 8001)
        self.assertEqual(s['subject_code'], "CS101")
        self.assertEqual(s['attempts'], 2)
        self.assertAlmostEqual(s['first_gp'], 0.0, places=1,
            msg="first_gp must be 0.0 (chronologically first attempt by exam_id=6001)")
        self.assertAlmostEqual(s['best_gp'], 3.0, places=1)
        self.assertTrue(s['passed_after_retake'],
            "passed_after_retake must be True: first_gp < 2.0 and best_gp >= 2.0")
        self.assertAlmostEqual(s['gp_gain'], 3.0, places=1)

        # Edge case: first attempt PASSED (gp=3.5), retake lowered to 2.0 → NOT passed_after_retake
        retake_profile2 = "retake_test_profile2"
        with database.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)",
                (retake_profile2, "89", SESS_ID, time.time())
            )
            conn.execute(
                "INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)",
                (retake_profile2, 8002, "Pass First", SESS_ID)
            )
            conn.execute("""
                INSERT OR REPLACE INTO subject_grades
                (profile_name, reg_no, exam_id, subject_code, grade_point, credit_hours, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (retake_profile2, 8002, "7001", "MA101", 3.5, 3.0, SESS_ID))
            conn.execute("""
                INSERT OR REPLACE INTO subject_grades
                (profile_name, reg_no, exam_id, subject_code, grade_point, credit_hours, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (retake_profile2, 8002, "7002", "MA101", 2.0, 3.0, SESS_ID))
            conn.commit()

        stats2 = database.get_retake_success_stats(retake_profile2)
        self.assertEqual(len(stats2), 1)
        s2 = stats2[0]
        self.assertAlmostEqual(s2['first_gp'], 3.5, places=1,
            msg="first_gp must be 3.5 (chronologically first attempt by exam_id=7001)")
        self.assertFalse(s2['passed_after_retake'],
            "passed_after_retake must be False: first_gp >= 2.0 already passed")

    # ------------------------------------------------------------------
    # 9. Longitudinal semester parsing & filtering
    # ------------------------------------------------------------------
    def test_get_longitudinal_data_parsing_and_filtering(self):
        long_profile = "long_test_profile"
        with database.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)",
                (long_profile, "90", SESS_ID, time.time())
            )
            conn.execute(
                "INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)",
                (long_profile, 9001, "Long Student", SESS_ID)
            )
            # Add different exams
            # 1. Standard: "1st Year 2nd Semester" -> sem_num = 2
            # 2. Consecutive: "3rd Year 6th Semester" -> sem_num = 6
            # 3. Year-omitted: "5th Semester" -> sem_num = 5
            # 4. Unparseable: "Orientation Exam" -> sem_num = 0 (should be excluded)
            conn.execute("""
                INSERT OR REPLACE INTO exam_results 
                (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (long_profile, 9001, "9001", "1st Year 2nd Semester Exam", 3.5, 3.5, "Promoted", SESS_ID))
            conn.execute("""
                INSERT OR REPLACE INTO exam_results 
                (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (long_profile, 9001, "9002", "3rd Year 6th Semester Exam", 3.6, 3.6, "Promoted", SESS_ID))
            conn.execute("""
                INSERT OR REPLACE INTO exam_results 
                (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (long_profile, 9001, "9003", "5th Semester Exam", 3.7, 3.7, "Promoted", SESS_ID))
            conn.execute("""
                INSERT OR REPLACE INTO exam_results 
                (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (long_profile, 9001, "9004", "Orientation Exam", 4.0, 4.0, "Promoted", SESS_ID))
            conn.commit()

        data = database.get_longitudinal_data(long_profile)
        self.assertIn(9001, data)
        records = data[9001]
        
        # Verify Orientation (sem_num=0) is filtered out
        sem_nums = [r['semester_num'] for r in records]
        self.assertNotIn(0, sem_nums, "sem_num=0 records must be excluded from longitudinal data")
        
        # Verify the semester numbers sorted: 2, 5, 6
        self.assertEqual(sem_nums, [2, 5, 6])
        
        # Verify specific details
        self.assertEqual(records[0]['semester_num'], 2)
        self.assertEqual(records[1]['semester_num'], 5)
        self.assertEqual(records[2]['semester_num'], 6)


    def test_compute_per_semester_breakdown_adjusted_and_fallback(self):
        # CSE-1102 has gp=2.75, original_gp=2.25
        effective_grades = {
            "CSE-1102": {"gp": 2.75, "original_gp": 2.25, "credit": 3.0, "source": "improvement_cleared", "name": "Intro CS"}
        }
        breakdown = database.compute_per_semester_breakdown(
            effective_grades=effective_grades,
            dept="CSE",
            current_semester=1,
            overrides={}
        )
        self.assertEqual(len(breakdown), 1)
        # computed_gpa should now contain Adjusted GPA (2.75)
        self.assertAlmostEqual(breakdown[0]["computed_gpa"], 2.75, places=2)
        self.assertAlmostEqual(breakdown[0]["computed_cgpa"], 2.75, places=2)
        # official_gpa and official_cgpa (being missing/0.00) should fall back to original main grades (2.25)
        self.assertAlmostEqual(breakdown[0]["official_gpa"], 2.25, places=2)
        self.assertAlmostEqual(breakdown[0]["official_cgpa"], 2.25, places=2)

    def test_compute_advanced_projection_shows_correct_already_attempted_reason(self):
        # CSE-1102 has gp=2.75, original_gp=2.25, source="improvement_cleared"
        deep_result = {
            'true_cgpa': 2.75,
            'total_credits': 3.0
        }
        effective_grades = {
            "CSE-1102": {"gp": 2.75, "original_gp": 2.25, "credit": 3.0, "source": "improvement_cleared", "name": "Intro CS"}
        }
        adv = database.compute_advanced_projection(
            deep_result=deep_result,
            effective_grades=effective_grades,
            retake_records=[],
            profile_name=""
        )
        self.assertEqual(len(adv["already_attempted"]), 1)
        aa = adv["already_attempted"][0]
        self.assertEqual(aa["code"], "CSE-1102")
        self.assertEqual(aa["reason"], "Increased by 0.50 (from 2.25), but still improvable")


    def test_compute_graduation_projection_uses_adj_cgpa_and_credits(self):
        deep_result = {
            'true_cgpa': 3.0,
            'total_credits': 100.0,
            'current_semester': 5
        }
        res = database.compute_graduation_projection(
            deep_result=deep_result,
            target_grad_cgpa=3.50,
            dept="CSE"
        )
        self.assertAlmostEqual(res["current_true_cgpa"], 3.0, places=2)

        res_adj = database.compute_graduation_projection(
            deep_result=deep_result,
            target_grad_cgpa=3.50,
            dept="CSE",
            adj_cgpa=3.20,
            adj_credits=100.0
        )
        self.assertAlmostEqual(res_adj["current_true_cgpa"], 3.2, places=2)
        self.assertTrue(res_adj["required_avg_gpa"] < res["required_avg_gpa"])


    def test_get_semester_from_code_unhyphenated(self):
        # Test that unhyphenated subject codes are parsed correctly
        self.assertEqual(database.get_semester_from_code("CSE1101", "CSE"), 1)
        self.assertEqual(database.get_semester_from_code("CSE-1101", "CSE"), 1)
        self.assertEqual(database.get_semester_from_code("CSE 1101", "CSE"), 1)
        self.assertEqual(database.get_semester_from_code("CE101", "civil"), 1)
        self.assertEqual(database.get_semester_from_code("CE-101", "civil"), 1)
        self.assertEqual(database.get_semester_from_code("CE 101", "civil"), 1)
        self.assertEqual(database.get_semester_from_code("CSE1101**", "CSE"), 1)

    def test_fallback_calculations_with_null_credits(self):
        # Seed student record with a missing GPA/CGPA and None/null credit_hours in subject_grades
        results = [
            {
                "Registration No": 1001,
                "Name": "Test Student",
                "CGPA": "-",
                "GPA": "-",
                "Result": "Promoted",
                "_sess_id": SESS_ID,
                "_exam_id": EXAM_ID,
                "Subjects": [
                    {"code": "CS101", "name": "Intro CS", "grade": "A", "gp": "4.00"},
                    {"code": "MA101", "name": "Math",     "grade": "B", "gp": "3.00"},
                ],
            }
        ]
        # We need to save the profile first so foreign key constraints pass
        with database.get_connection() as conn:
            conn.execute("INSERT INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, 0)", (PROFILE, PRO_ID, SESS_ID))
            conn.commit()
            
        database.save_profile_and_results(PROFILE, PRO_ID, SESS_ID, results, EXAM_ID, EXAM_NM)
        
        # Now we manually update the credit_hours of the subject grades to None/NULL to simulate unmapped subjects
        with database.get_connection() as conn:
            conn.execute("UPDATE subject_grades SET credit_hours = NULL WHERE profile_name=? AND reg_no=?", (PROFILE, 1001))
            conn.commit()

        # Call get_student_data_for_exam which triggers GPA & CGPA fallbacks
        student_data = database.get_student_data_for_exam(PROFILE, EXAM_ID)
        self.assertEqual(len(student_data), 1)
        # Fallback credit hour is 3.0.
        # GPA = (4.0 * 3.0 + 3.0 * 3.0) / (3.0 + 3.0) = 3.50
        # CGPA = same = 3.50
        self.assertAlmostEqual(student_data[0]["gpa"], 3.50, places=2)
        self.assertAlmostEqual(student_data[0]["cgpa"], 3.50, places=2)

    def test_get_batch_max_semester_and_filtering(self):
        batch_profile = "batch_test_profile"
        with database.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles (name, pro_id, sess_id, timestamp) VALUES (?, ?, ?, ?)",
                (batch_profile, "91", SESS_ID, time.time())
            )
            conn.commit()

        # Seed student roster properly (Alice: 1001, Bob: 1002, Readmitted: 1003)
        with database.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)", (batch_profile, 1001, "Alice", SESS_ID))
            conn.execute("INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)", (batch_profile, 1002, "Bob", SESS_ID))
            conn.execute("INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)", (batch_profile, 1003, "Readd", SESS_ID))
            conn.commit()

        # Add exam results
        # Sem 1: Alice, Bob, Readd have results
        # Sem 2: Alice, Bob, Readd have results
        # Sem 3: Alice, Bob, Readd have results
        # Sem 4 (Future): Only Readd has results
        with database.get_connection() as conn:
            # Sem 1
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1001, "101", "1st Year 1st Semester Exam", 3.0, 3.0, "Promoted", SESS_ID))
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1002, "101", "1st Year 1st Semester Exam", 3.1, 3.1, "Promoted", SESS_ID))
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1003, "101", "1st Year 1st Semester Exam", 3.2, 3.2, "Promoted", SESS_ID))
            
            # Sem 2
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1001, "102", "1st Year 2nd Semester Exam", 3.0, 3.0, "Promoted", SESS_ID))
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1002, "102", "1st Year 2nd Semester Exam", 3.1, 3.1, "Promoted", SESS_ID))
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1003, "102", "1st Year 2nd Semester Exam", 3.2, 3.2, "Promoted", SESS_ID))
            
            # Sem 3
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1001, "103", "2nd Year 1st Semester Exam", 3.0, 3.0, "Promoted", SESS_ID))
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1002, "103", "2nd Year 1st Semester Exam", 3.1, 3.1, "Promoted", SESS_ID))
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1003, "103", "2nd Year 1st Semester Exam", 3.2, 3.2, "Promoted", SESS_ID))
            
            # Sem 4 (Only Readd student)
            conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, 1003, "104", "2nd Year 2nd Semester Exam", 3.2, 3.2, "Promoted", SESS_ID))
            conn.commit()

        # Max semester should be 3 (since only 1 student has Sem 4, which is less than the threshold of min(5, max_cohort_size // 2) = min(5, 3 // 2) = 1... wait, max_cohort_size is 3. 3 // 2 is 1. max(1, 1) = 1. min(5, 1) = 1.
        # Oh, if max_cohort_size is 3, threshold is min(5, max(1, 3//2)) = min(5, 1) = 1.
        # If threshold is 1, then Sem 4 (which has 1 student) would be considered valid!
        # Wait, is that true? Let's check:
        # If cohort size is 3, a readmitted student makes up 1/3 of the batch.
        # Wait, if we want readmitted students to be filtered out, we want threshold to be:
        # max(2, max_cohort_size // 2) or something?
        # Let's think: what if cohort size is small (e.g. 3 or 5)?
        # Let's see: in a real department, cohort size is at least 30-60 students. A cohort size of 3 is a test case.
        # For a real batch of e.g. 50 students, cohort size is 50, threshold = min(5, 25) = 5. So it requires 5 students.
        # Let's write a test where Alice, Bob, and 5 other students (say, total 7 students) are in the batch, and only 1 student (the readmitted one) has Sem 4.
        # In that case, max_cohort_size = 7. Threshold = min(5, max(1, 7//2)) = min(5, 3) = 3.
        # Since only 1 student has Sem 4, 1 < 3, so Sem 4 will be correctly filtered out!
        # Let's write the test case with a slightly larger cohort to test the threshold behavior properly.

        # Let's register 7 students (1001-1007)
        with database.get_connection() as conn:
            for i in range(1004, 1008):
                conn.execute("INSERT OR IGNORE INTO students (profile_name, reg_no, name, sess_id) VALUES (?, ?, ?, ?)", (batch_profile, i, f"Student {i}", SESS_ID))
            conn.commit()

        # And insert Sem 1-3 results for all 7 students
        with database.get_connection() as conn:
            for i in range(1004, 1008):
                conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, i, "101", "1st Year 1st Semester Exam", 3.0, 3.0, "Promoted", SESS_ID))
                conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, i, "102", "1st Year 2nd Semester Exam", 3.0, 3.0, "Promoted", SESS_ID))
                conn.execute("INSERT INTO exam_results (profile_name, reg_no, exam_id, exam_name, gpa, cgpa, result_status, sess_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (batch_profile, i, "103", "2nd Year 1st Semester Exam", 3.0, 3.0, "Promoted", SESS_ID))
            conn.commit()

        max_sem = database.get_batch_max_semester(batch_profile)
        self.assertEqual(max_sem, 3, "Batch max semester should be 3, since only 1 student has semester 4 results out of 7 total cohort size")

        # Verify longitudinal data filtering
        data_all = database.get_longitudinal_data(batch_profile)
        data_filtered = database.get_longitudinal_data(batch_profile, max_semester=max_sem)

        # In data_all, Readd (1003) has 4 semesters
        self.assertEqual(len(data_all[1003]), 4)
        self.assertEqual(data_all[1003][-1]['semester_num'], 4)

        # In data_filtered, Readd (1003) should only have 3 semesters
        self.assertEqual(len(data_filtered[1003]), 3)
        self.assertEqual(data_filtered[1003][-1]['semester_num'], 3)

    def test_get_performance_archetypes_and_insights_three_states(self):
        import pandas as pd
        df_pivot = pd.DataFrame(
            [[3.0, 3.5], [3.5, 3.8], [2.0, 1.5], [3.2, 3.3]],
            index=[1001, 1002, 1003, 1004],
            columns=['CSE-1101', 'CSE-1201']
        )
        df_main = pd.DataFrame([
            {'reg_no': 1001, 'name': 'Alice', 'gpa': 3.5, 'cgpa': 3.25, 'sess_id': '42'},
            {'reg_no': 1002, 'name': 'Bob', 'gpa': 3.8, 'cgpa': 3.65, 'sess_id': '42'},
            {'reg_no': 1003, 'name': 'Charlie', 'gpa': 1.5, 'cgpa': 1.75, 'sess_id': '42'},
            {'reg_no': 1004, 'name': 'David', 'gpa': 3.3, 'cgpa': 3.25, 'sess_id': '42'},
        ])
        
        archetypes = database.get_performance_archetypes(df_pivot, df_main, promo_target=2.00, promo_yr=1)
        self.assertIsNotNone(archetypes)
        self.assertEqual(len(archetypes), 4)
        
        self.assertEqual(archetypes.loc[1001]['Detailed_Status'], 'On-Track')
        self.assertEqual(archetypes.loc[1002]['Detailed_Status'], 'Exceeding')
        self.assertEqual(archetypes.loc[1003]['Detailed_Status'], 'At-Risk')
        
        df_sub = pd.DataFrame([
            {'subject_code': 'CSE-1101', 'subject_name': 'Intro CS', 'gp': 3.0, 'reg_no': 1001},
            {'subject_code': 'CSE-1101', 'subject_name': 'Intro CS', 'gp': 2.0, 'reg_no': 1003},
        ])
        insights = database.get_strategic_insights(df_main, df_sub, df_pivot, archetypes)
        
        self.assertEqual(insights['risk_count'], 1)
        self.assertEqual(len(insights['risk_students']), 1)
        self.assertEqual(insights['risk_students'][0][0], 1003)


if __name__ == "__main__":
    unittest.main(verbosity=2)
