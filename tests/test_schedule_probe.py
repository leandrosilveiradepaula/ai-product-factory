import json
import unittest

from ai_product_factory.schedule_probe import SupabaseScheduleProbe


class StubProbe(SupabaseScheduleProbe):
    def __init__(
        self,
        *,
        runs=None,
        tasks=None,
        pending_units=None,
        change_sets=None,
        lanes=None,
        telemetry_error=None,
    ):
        self.rows = {
            "factory_runs": list(runs or []),
            "factory_tasks": list(tasks or []),
            "factory_change_set_work_units": list(pending_units or []),
            "factory_change_sets": list(change_sets or []),
            "factory_specialist_lane_jobs": list(lanes or []),
        }
        self.telemetry_posts = []
        self.telemetry_error = telemetry_error

    def _get(self, path: str):
        for table, rows in self.rows.items():
            if path.startswith(table + "?"):
                return list(rows)
        raise AssertionError(f"unexpected path: {path}")

    def _post(self, path: str, payload: dict) -> None:
        self.telemetry_posts.append((path, payload))
        if self.telemetry_error:
            raise self.telemetry_error


class ScheduleProbeTests(unittest.TestCase):
    def assert_telemetry(self, probe, *, work_detected, work_classes):
        self.assertEqual(
            probe.telemetry_posts,
            [
                (
                    "factory_audit_events",
                    {
                        "actor_type": "system",
                        "actor_ref": "schedule-probe",
                        "event_type": "schedule_probe.observed",
                        "payload": {
                            "work_detected": work_detected,
                            "work_classes": work_classes,
                        },
                    },
                )
            ],
        )

    def test_empty_control_plane_reports_no_work_and_records_durable_telemetry(self):
        probe = StubProbe()
        out = probe.probe()

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
        self.assertTrue(out["telemetry_recorded"])
        self.assert_telemetry(probe, work_detected=False, work_classes=[])

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

    def test_individual_work_signals_record_normalized_work_classes(self):
        cases = {
            "product": {
                "runs": [{"id": "r1", "task_id": "t1", "status": "created"}],
                "tasks": [{"id": "t1", "status": "queued"}],
            },
            "dispatch": {"pending_units": [{"id": "unit-1"}]},
            "integration": {"change_sets": [{"id": "change-set-1"}]},
            "ci": {"runs": [{"id": "r1", "status": "ci_pending"}]},
            "specialist_security": {"lanes": [{"role": "security"}]},
            "specialist_qa": {"lanes": [{"role": "qa"}]},
            "specialist_operations": {"lanes": [{"role": "operations"}]},
            "preview": {"runs": [{"id": "r1", "status": "preview_ready"}]},
            "release": {"runs": [{"id": "r1", "status": "awaiting_release"}]},
            "codex_manual": {"runs": [{"id": "r1", "status": "awaiting_codex_manual"}]},
        }

        for work_class, kwargs in cases.items():
            with self.subTest(work_class=work_class):
                probe = StubProbe(**kwargs)
                out = probe.probe()

                self.assertTrue(out["work_detected"])
                self.assertTrue(out["telemetry_recorded"])
                self.assert_telemetry(probe, work_detected=True, work_classes=[work_class])

    def test_specialist_roles_are_normalized_and_sorted_in_telemetry(self):
        probe = StubProbe(
            lanes=[
                {"role": "operations"},
                {"role": "security"},
                {"role": "qa"},
                {"role": "unrecognized-role"},
                {"role": "security"},
            ]
        )
        out = probe.probe()

        self.assertEqual(out["specialist_roles"], ["operations", "qa", "security"])
        self.assert_telemetry(
            probe,
            work_detected=True,
            work_classes=[
                "specialist_security",
                "specialist_qa",
                "specialist_operations",
            ],
        )

    def test_telemetry_relies_on_audit_default_timestamp_and_excludes_sensitive_rows(self):
        secret = "not-a-production-credential"
        probe = StubProbe(
            runs=[
                {
                    "id": "r1",
                    "task_id": "t1",
                    "status": "created",
                    "authorization": secret,
                    "headers": {"X-Internal": secret},
                    "error": "free-form upstream failure detail",
                }
            ],
            tasks=[{"id": "t1", "status": "queued", "raw_row": {"token": secret}}],
        )
        out = probe.probe()

        self.assertTrue(out["telemetry_recorded"])
        path, event = probe.telemetry_posts[0]
        self.assertEqual(path, "factory_audit_events")
        self.assertEqual(
            event,
            {
                "actor_type": "system",
                "actor_ref": "schedule-probe",
                "event_type": "schedule_probe.observed",
                "payload": {"work_detected": True, "work_classes": ["product"]},
            },
        )

        # The audit table owns the event time via its database default; probes do
        # not claim a static or client-generated timestamp in durable telemetry.
        encoded_event = json.dumps(event, sort_keys=True)
        for forbidden in (
            secret,
            "authorization",
            "headers",
            "raw_row",
            "free-form upstream failure detail",
            "created_at",
            "observed_at",
            "timestamp",
        ):
            self.assertNotIn(forbidden, encoded_event)

    def test_telemetry_write_failure_preserves_work_detection(self):
        probe = StubProbe(
            runs=[{"id": "r1", "status": "ci_pending"}],
            telemetry_error=RuntimeError("persistence error detail must not be reported"),
        )
        out = probe.probe()

        self.assertTrue(out["work_detected"])
        self.assertTrue(out["ci_work"])
        self.assertFalse(out["telemetry_recorded"])
        self.assertNotIn("telemetry_error", out)
        self.assertNotIn("persistence error detail must not be reported", str(out))
        self.assert_telemetry(probe, work_detected=True, work_classes=["ci"])


if __name__ == "__main__":
    unittest.main()
