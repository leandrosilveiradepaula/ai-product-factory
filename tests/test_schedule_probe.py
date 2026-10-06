import json
import unittest

from ai_product_factory.schedule_probe import SupabaseScheduleProbe


class StubProbe(SupabaseScheduleProbe):
    def __init__(self, *, runs=None, tasks=None, pending_units=None, change_sets=None, lanes=None):
        self.rows = {
            "factory_runs": list(runs or []),
            "factory_tasks": list(tasks or []),
            "factory_change_set_work_units": list(pending_units or []),
            "factory_change_sets": list(change_sets or []),
            "factory_specialist_lane_jobs": list(lanes or []),
        }

    def _get(self, path: str):
        for table, rows in self.rows.items():
            if path.startswith(table + "?"):
                return list(rows)
        raise AssertionError(f"unexpected path: {path}")


class ScheduleProbeTests(unittest.TestCase):
    def test_empty_control_plane_reports_no_work(self):
        out = StubProbe().probe()
        self.assertFalse(out["work_detected"])
        self.assertFalse(out["product_work"])
        self.assertFalse(out["dispatch_work"])
        self.assertFalse(out["integration_work"])
        self.assertFalse(out["ci_work"])
        self.assertFalse(out["specialist_work"])
        self.assertFalse(out["specialist_security_work"])
        self.assertFalse(out["specialist_qa_work"])
        self.assertFalse(out["specialist_operations_work"])
        self.assertFalse(out["preview_work"])
        self.assertFalse(out["release_work"])
        self.assertFalse(out["codex_manual_work"])

    def test_no_work_telemetry_has_no_work_classes(self):
        out = StubProbe().probe()

        self.assertEqual(out["work_classes"], [])
        self.assertEqual(
            out["telemetry"],
            {"work_detected": False, "work_classes": []},
        )

    def test_product_stage_requires_queued_task(self):
        out = StubProbe(
            runs=[{"id": "r1", "task_id": "t1", "status": "created", "execution_route": None}],
            tasks=[{"id": "t1", "status": "queued"}],
        ).probe()
        self.assertTrue(out["product_work"])
        self.assertTrue(out["work_detected"])

        blocked = StubProbe(
            runs=[{"id": "r1", "task_id": "t1", "status": "created", "execution_route": None}],
            tasks=[{"id": "t1", "status": "queued_execution"}],
        ).probe()
        self.assertFalse(blocked["product_work"])

    def test_detected_work_telemetry_is_normalized_and_sanitized(self):
        secret = "super-secret-token"
        raw_run = {
            "id": "r-sensitive",
            "task_id": "t-sensitive",
            "status": "created",
            "execution_route": "direct",
            "access_token": secret,
            "source_row": {"private_key": secret},
        }
        raw_task = {
            "id": "t-sensitive",
            "status": "queued",
            "service_role_key": secret,
        }

        out = StubProbe(runs=[raw_run], tasks=[raw_task]).probe()
        serialized = json.dumps(out, sort_keys=True)

        self.assertTrue(out["work_detected"])
        self.assertEqual(out["work_classes"], ["product"])
        self.assertEqual(
            out["telemetry"],
            {"work_detected": True, "work_classes": ["product"]},
        )
        self.assertNotIn(raw_run["id"], serialized)
        self.assertNotIn(raw_task["id"], serialized)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("service_role_key", serialized)
        self.assertNotIn("source_row", serialized)
        self.assertNotIn("private_key", serialized)

    def test_manual_codex_detects_prepare_and_followup(self):
        preparing = StubProbe(
            runs=[{"id": "r1", "task_id": "t1", "status": "queued", "execution_route": "codex"}],
            tasks=[{"id": "t1", "status": "queued_execution"}],
        ).probe()
        self.assertTrue(preparing["codex_manual_work"])

        waiting = StubProbe(
            runs=[{"id": "r2", "task_id": "t2", "status": "awaiting_codex_manual", "execution_route": "codex"}],
        ).probe()
        self.assertTrue(waiting["codex_manual_work"])

    def test_pipeline_followup_flags_are_independent(self):
        out = StubProbe(
            runs=[
                {"id": "r1", "task_id": "t1", "status": "ci_pending", "execution_route": "direct"},
                {"id": "r2", "task_id": "t2", "status": "preview_ready", "execution_route": "direct"},
                {"id": "r3", "task_id": "t3", "status": "awaiting_release", "execution_route": "direct"},
            ],
            pending_units=[{"id": "u1"}],
            change_sets=[{"id": "c1"}],
            lanes=[{"role": "security"}, {"role": "qa"}],
        ).probe()
        self.assertTrue(out["dispatch_work"])
        self.assertTrue(out["integration_work"])
        self.assertTrue(out["ci_work"])
        self.assertTrue(out["specialist_work"])
        self.assertEqual(out["specialist_roles"], ["qa", "security"])
        self.assertTrue(out["specialist_security_work"])
        self.assertTrue(out["specialist_qa_work"])
        self.assertFalse(out["specialist_operations_work"])
        self.assertTrue(out["preview_work"])
        self.assertTrue(out["release_work"])
        self.assertTrue(out["work_detected"])


if __name__ == "__main__":
    unittest.main()
