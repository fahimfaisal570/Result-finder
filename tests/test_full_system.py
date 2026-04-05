"""
tests/test_full_system.py — Comprehensive System Check
Verifies CLI BatchManager <-> Database <-> Analytics Sync.
"""
import os, sys, tempfile, unittest
from unittest.mock import patch

# Force SQLite to use a temporary DB for testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
TEST_DB = _tmp.name

import database as db
db.DB_PATH = TEST_DB
db.init_db()
db.migrate_schema_v2()

import cli_scraper as cs

class TestFullSystem(unittest.TestCase):
    def setUp(self):
        # Clean the test DB before each run
        with db.get_connection() as conn:
            conn.executescript("""
                DELETE FROM subject_grades;
                DELETE FROM exam_results;
                DELETE FROM scan_log;
                DELETE FROM students;
                DELETE FROM profiles;
            """)
            conn.commit()

    def test_cli_batch_manager_db_sync(self):
        """Verify that CLI BatchManager correctly interacts with SQLite."""
        bm = cs.BatchManager()
        
        # 1. Create Profile
        regs_data = [
            [1001, "2022-23", "Alice Student"],
            [1002, "2022-23", "Bob Student"]
        ]
        bm.save_new_batch("SyncTest", regs_data, sess_id="22", pro_id="14", latest_exam_id="50")
        
        # 2. Verify creation in DB
        profiles = db.get_profiles()
        self.assertIn("SyncTest", profiles)
        self.assertEqual(profiles["SyncTest"]["pro_id"], "14")
        self.assertEqual(len(profiles["SyncTest"]["regs"]), 2)
        
        # 3. Add student
        bm.add_to_batch("SyncTest", [[1003, "2022-23", "Charlie Student"]])
        profiles_after_add = db.get_profiles()
        self.assertEqual(len(profiles_after_add["SyncTest"]["regs"]), 3)
        
        # 4. Remove student
        bm.remove_from_batch("SyncTest", [1002])
        profiles_after_rem = db.get_profiles()
        self.assertEqual(len(profiles_after_rem["SyncTest"]["regs"]), 2)
        regs_left = [r[0] for r in profiles_after_rem["SyncTest"]["regs"]]
        self.assertNotIn(1002, regs_left)
        
        # 5. Delete Profile
        bm.delete_batch("SyncTest")
        self.assertNotIn("SyncTest", db.get_profiles())

    def test_retake_improvement_logic(self):
        """Verify that analytics correctly identifies grade improvements via retakes."""
        profile = "RetakeTest"
        exam1_results = [{
            "Registration No": 999,
            "Name": "Retake Roy",
            "GPA": "2.00", "CGPA": "2.00",
            "Subjects": [{"code": "MAT101", "name": "Math", "grade": "D", "gp": "2.00"}]
        }]
        # Initial scan
        db.save_profile_and_results(profile, "14", "22", exam1_results, "E100", "Main Exam")
        
        # Check initial CGPA
        eff1 = db.get_effective_cgpa_per_student(profile)
        self.assertEqual(eff1[0]['effective_cgpa'], 2.0)
        self.assertEqual(eff1[0]['improvement_count'], 1) # 2.0 is an improvement candidate
        
        # Retake scan (Higher Grade)
        exam2_results = [{
            "Registration No": 999,
            "Name": "Retake Roy",
            "GPA": "4.00", "CGPA": "3.00",
            "Subjects": [{"code": "MAT101", "name": "Math", "grade": "A+", "gp": "4.00"}]
        }]
        db.save_exam_analytics_only(profile, "E200", "Retake Exam", exam2_results)
        
        # Check improved CGPA
        eff2 = db.get_effective_cgpa_per_student(profile)
        self.assertEqual(eff2[0]['effective_cgpa'], 4.0)
        self.assertEqual(eff2[0]['improvement_count'], 0) # 4.0 is NOT an improvement candidate
        
        # Retake scan (Lower Grade - Should be ignored by effective CGPA)
        exam3_results = [{
            "Registration No": 999,
            "Name": "Retake Roy",
            "GPA": "3.00", "CGPA": "3.50",
            "Subjects": [{"code": "MAT101", "name": "Math", "grade": "B", "gp": "3.00"}]
        }]
        db.save_exam_analytics_only(profile, "E300", "Poor Retake", exam3_results)
        
        eff3 = db.get_effective_cgpa_per_student(profile)
        self.assertEqual(eff3[0]['effective_cgpa'], 4.0) # Still 4.0!
        self.assertEqual(eff3[0]['improvement_count'], 0)

    def tearDown(self):
        # We don't manually delete the file here to avoid PermissionError on Windows.
        # Temp files are cleaned up by OS eventually or when the process ends.
        pass

if __name__ == "__main__":
    unittest.main()
