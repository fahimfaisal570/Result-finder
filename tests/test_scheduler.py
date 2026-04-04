"""
tests/test_scheduler.py
Tests the background scheduler cycle logic without making actual network calls.
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

class TestScheduler(unittest.TestCase):
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
    def test_scheduler_cycle(self, mock_scan, mock_fetch):
        # 1. Setup mock data
        database.save_profile_and_results("test_auto", "14", "22", [
            {"Registration No": 1001, "Name": "Bob"}
        ], "100", "Initial")
        
        config.SCAN_ONLY_PROFILES = []
        config.SCAN_INTERVAL_MINUTES = 30
        
        # Mock up fetch_exams returning one new exam
        mock_fetch.return_value = {"200": "Test Auto Exam"}
        
        # Mock up run_batch_scan_engine returning one result
        mock_scan.return_value = [
            {"Registration No": 1001, "Name": "Bob", "CGPA": "3.9", "Result": "Promoted"}
        ]
        
        # 2. Run cycle
        scheduler.run_scheduler_cycle()
        
        # 3. Assertions
        mock_fetch.assert_called_once_with("14")
        mock_scan.assert_called_once()
        
        # Verify db saved it
        with database.get_connection() as conn:
            cur = conn.execute("SELECT cgpa FROM exam_results WHERE profile_name='test_auto' AND exam_id='200'")
            cgpa = cur.fetchone()[0]
            self.assertEqual(cgpa, 3.9)
            
            cur = conn.execute("SELECT count(*) FROM scan_log WHERE profile_name='test_auto' AND exam_id='200'")
            self.assertEqual(cur.fetchone()[0], 1)

if __name__ == "__main__":
    unittest.main()
