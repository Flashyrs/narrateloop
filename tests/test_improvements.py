import os
import sys
import unittest
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.db_utils import (
    init_db, get_or_create_job, update_job_stage, get_job,
    record_run_metrics, check_api_quota, increment_api_quota,
    get_pipeline_summary, QuotaExceededError
)
from utils.retry_utils import retry_with_backoff, is_transient_error
from utils.metrics_utils import ResourceTracker

class TestPipelineImprovements(unittest.TestCase):

    def setUp(self):
        init_db()
        self.test_date = "20991231"
        self._clean_test_records()

    def tearDown(self):
        self._clean_test_records()

    def _clean_test_records(self):
        from utils.db_utils import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pipeline_jobs WHERE date_str IN ('20991231', '20991230')")
            cursor.execute("DELETE FROM pipeline_runs WHERE job_key LIKE '2099%'")
            cursor.execute("DELETE FROM api_quota_tracking WHERE date_str IN ('20991231', '20991230')")
            conn.commit()

    def test_sqlite_state_transitions(self):
        # 1. Create job
        job = get_or_create_job(self.test_date, 1, "Test Story 1", "message_short")
        self.assertEqual(job["stage"], "PENDING")
        self.assertEqual(job["story_index"], 1)

        # 2. Transition through stages
        stages = ["PROCESSING", "TTS_DONE", "SUBS_DONE", "RENDER_DONE", "VALIDATED", "UPLOADED"]
        for stage in stages:
            update_job_stage(self.test_date, 1, stage)
            current = get_job(self.test_date, 1)
            self.assertEqual(current["stage"], stage)

        # 3. Test failure recording with error message
        update_job_stage(self.test_date, 1, "FAILED", error_message="Simulated test render error")
        failed_job = get_job(self.test_date, 1)
        self.assertEqual(failed_job["stage"], "FAILED")
        self.assertIn("Simulated test render error", failed_job["error_message"])
        self.assertGreater(failed_job["retry_count"], 0)

    def test_resource_tracker_metrics(self):
        tracker = ResourceTracker(target_dir=PROJECT_ROOT).start()
        # Simulate small work
        _ = sum(i * i for i in range(100000))
        metrics, log_str = tracker.finish()

        self.assertIn("wall_time_sec", metrics)
        self.assertIn("cpu_time_sec", metrics)
        self.assertIn("peak_rss_mb", metrics)
        self.assertIn("swap_delta_mb", metrics)
        self.assertIn("output_size_mb", metrics)
        self.assertIn("[Render Metrics]", log_str)

        # Record metrics to SQLite
        record_run_metrics(f"{self.test_date}_1", "RENDER", metrics, status="SUCCESS")
        summary = get_pipeline_summary(self.test_date)
        self.assertTrue(len(summary["recent_runs"]) > 0)

    def test_retry_transient_vs_permanent(self):
        # 1. Transient Error Simulation (429 Rate Limit) -> Should retry and succeed
        call_count = {"count": 0}

        @retry_with_backoff(max_retries=3, initial_delay=0.05, backoff_factor=1.5, jitter=False)
        def transient_function():
            call_count["count"] += 1
            if call_count["count"] < 3:
                raise Exception("HTTP 429 Rate limit exceeded")
            return "SUCCESS"

        result = transient_function()
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(call_count["count"], 3)

        # 2. Permanent Error Simulation (401 Unauthorized) -> Should fail immediately without retry
        perm_call_count = {"count": 0}

        @retry_with_backoff(max_retries=3, initial_delay=0.05, backoff_factor=1.5, jitter=False)
        def permanent_function():
            perm_call_count["count"] += 1
            raise Exception("HTTP 401 Invalid credentials / Unauthorized")

        with self.assertRaises(Exception):
            permanent_function()

        self.assertEqual(perm_call_count["count"], 1)

    def test_free_tier_quota_guard(self):
        test_quota_date = "20991230"
        os.environ["MAX_AI_REQUESTS_PER_DAY"] = "2"

        # Check within quota
        self.assertTrue(check_api_quota("ai", date_str=test_quota_date))
        increment_api_quota("ai", date_str=test_quota_date, success=True)
        increment_api_quota("ai", date_str=test_quota_date, success=True)

        # Exceed quota
        with self.assertRaises(QuotaExceededError):
            check_api_quota("ai", date_str=test_quota_date)

if __name__ == "__main__":
    unittest.main()
