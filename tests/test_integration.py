"""
tests/test_integration.py
End-to-End Integration test for save -> scheduler -> analytics.
"""
import os, sys, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
TEST_DB = _tmp.name

import database
database.DB_PATH = TEST_DB
database.init_db()
database.migrate_schema_v2()

import config
import scheduler
import pandas as pd

class TestIntegration(unittest.TestCase):
    def setUp(self):
        with database.get_connection() as conn:
            conn.executescript("""
                DELETE FROM subject_grades;
                DELETE FROM exam_results;
                DELETE FROM scan_log;
                DELETE FROM students;
                DELETE FROM profiles;
            """)
            conn.commit()

    @patch('cli_scraper.fetch_exams')
    @patch('cli_scraper.run_batch_scan_engine')
    def test_end_to_end_flow(self, mock_scan, mock_fetch):
        # ----------------------------------------------------
        # 1. User saves a profile manually (Simulate results.py)
        # ----------------------------------------------------
        initial_results = [
            {
                "Registration No": 5001,
                "Name": "Integration Charlie",
                "GPA": "3.00",
                "CGPA": "3.00",
                "Overall Result": "Promoted",
                "Subjects": [
                    {"code": "CS101", "name": "Intro", "grade": "B", "gp": "3.00"}
                ]
            }
        ]
        
        # Save profile
        database.save_profile_and_results("TestFlow", '14', '22', initial_results, '100', 'Semester 1')
        
        # Check Effective CGPA is 3.0
        eff = database.get_effective_cgpa_per_student("TestFlow")
        self.assertEqual(len(eff), 1)
        self.assertEqual(eff[0]['effective_cgpa'], 3.0)
        self.assertEqual(eff[0]['improvement_count'], 0)
        
        # ----------------------------------------------------
        # 2. Scheduler runs over time (Simulate scheduler.py)
        # ----------------------------------------------------
        config.SCAN_ONLY_PROFILES = []
        config.SCAN_INTERVAL_MINUTES = 0 # force run
        
        mock_fetch.return_value = {"200": "Semester 2 (With Retakes)"}
        mock_scan.return_value = [
            {
                "Registration No": 5001,
                "Name": "Integration Charlie",
                "GPA": "4.00",
                "CGPA": "3.80",
                "Overall Result": "Promoted",
                "Subjects": [
                    {"code": "CS101", "name": "Intro", "grade": "A+", "gp": "4.00"} # Retake improved!
                ]
            }
        ]
        
        # Run scheduler
        scheduler.run_scheduler_cycle()
        
        # ----------------------------------------------------
        # 3. Analytics engine pulls data (Simulate analytics.py)
        # ----------------------------------------------------
        new_eff = database.get_effective_cgpa_per_student("TestFlow")
        self.assertEqual(len(new_eff), 1)
        
        # Original was 3.0, new attempt on same subject got 4.0. 
        # But wait, the raw CGPA in the second exam is 3.80.
        # But our effective CGPA calc computes from subject_grades.
        # It's an average of highest grades. 
        # In this simplistic integration test, there's only 1 subject. Avg of 4.0 is 4.0.
        self.assertEqual(new_eff[0]['effective_cgpa'], 4.0)
        
        # Improvement count should be 1 because grade went up!
        self.assertEqual(new_eff[0]['improvement_count'], 1)
        
        # Ensure it works in Pandas as analytics.py expects
        df = pd.DataFrame(new_eff)
        self.assertTrue('effective_cgpa' in df.columns)
        self.assertEqual(df.iloc[0]['effective_cgpa'], 4.0)
        self.assertEqual(df.iloc[0]['result_status'], 'Promoted')

if __name__ == "__main__":
    unittest.main()
