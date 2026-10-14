import os
import unittest
from unittest.mock import patch
from tests.test_schedule_probe import StubProbe

class NativeHeartbeatTests(unittest.TestCase):
    def test_native_event_type(self):
        with patch.dict(os.environ,{"GITHUB_EVENT_NAME":"schedule"}):
            p=StubProbe()
            p.probe()
        self.assertEqual(p.telemetry_posts[0][1]["event_type"],"schedule_probe.native_observed")
    def test_backup_and_manual_do_not_impersonate_cron(self):
        for event in ("workflow_run","workflow_dispatch","issue_comment"):
            with self.subTest(event=event),patch.dict(os.environ,{"GITHUB_EVENT_NAME":event}):
                p=StubProbe()
                p.probe()
                self.assertEqual(p.telemetry_posts[0][1]["event_type"],"schedule_probe.observed")
    def test_native_telemetry_failure_is_fatal(self):
        with patch.dict(os.environ,{"GITHUB_EVENT_NAME":"schedule"}):
            with self.assertRaisesRegex(RuntimeError,"heartbeat could not be persisted"):
                StubProbe(telemetry_error=RuntimeError("write unavailable")).probe()
    def test_backup_telemetry_failure_remains_best_effort(self):
        with patch.dict(os.environ,{"GITHUB_EVENT_NAME":"workflow_run"}):
            result=StubProbe(telemetry_error=RuntimeError("write unavailable")).probe()
        self.assertFalse(result["telemetry_recorded"])

if __name__=="__main__":unittest.main()
