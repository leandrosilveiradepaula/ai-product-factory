import json
import unittest
from datetime import datetime, timedelta, timezone

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
        github_access=None,
        deployments=None,
        telemetry_error=None,
        portfolio_candidates=None,
        portfolio_error=None,
    ):
        self.rows = {
            "factory_runs": list(runs or []),
            "factory_tasks": list(tasks or []),
            "factory_change_set_work_units": list(pending_units or []),
            "factory_change_sets": list(change_sets or []),
            "factory_specialist_lane_jobs": list(lanes or []),
            "factory_project_github_access": list(github_access or []),
            "factory_deployments": list(deployments or []),
        }
        self.telemetry_posts = []
        self.telemetry_error = telemetry_error
        self.portfolio_candidates = list(portfolio_candidates or [])
        self.portfolio_error = portfolio_error
        self.probe_diagnostics = {}

    def _get(self, path: str):
        for table, rows in self.rows.items():
            if path.startswith(table + "?"):
                return list(rows)
        raise AssertionError(f"unexpected path: {path}")

    def _portfolio_dispatch_candidates(self):
        if self.portfolio_error:
            raise self.portfolio_error
        return self.portfolio_candidates

    def _post(self, path: str, payload: dict) -> None:
        self.telemetry_posts.append((path, payload))
        self.probe_diagnostics = payload["payload"]["queue_diagnostics"]
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
                            "queue_diagnostics": probe.probe_diagnostics,
                        },
                    },
                )
            ],
        )

    def test_empty_control_plane_reports_no_work_and_records_durable_telemetry(self):
        probe = StubProbe()
        out = probe.probe()

        self.assertFalse(out["work_detected"])
        self.assertFalse(out["github_access_work"])
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

    def test_stale_preview_runs_are_recorded_without_new_deployments(self):
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        fresh = datetime.now(timezone.utc).isoformat()
        probe = StubProbe(runs=[
            {"id": "r1", "status": "preview_ready", "created_at": old},
            {"id": "r2", "status": "preview_ready", "created_at": fresh},
            {"id": "r3", "status": "preview_ready", "created_at": "invalid"},
        ])
        out = probe.probe()
        self.assertEqual(out["queue_diagnostics"]["preview_ready_runs"], 3)
        self.assertEqual(out["queue_diagnostics"]["preview_ready_older_than_24h"], 1)
        self.assertEqual(probe.probe_diagnostics["preview_ready_older_than_24h"], 1)

    def test_orphan_queued_task_is_visible_without_triggering_paid_work(self):
        probe = StubProbe(tasks=[{"id": "t1", "status": "queued"}])
        out = probe.probe()
        self.assertFalse(out["work_detected"])
        self.assertEqual(out["queue_diagnostics"]["queued_without_product_run"], 1)

    def test_existing_queued_execution_run_wakes_dispatch_matrix(self):
        probe = StubProbe(
            tasks=[{"id": "t1", "status": "queued_execution"}],
            runs=[{"id": "r1", "task_id": "t1", "status": "queued", "execution_route": "direct"}],
        )
        out = probe.probe()
        self.assertTrue(out["dispatch_work"])
        self.assertTrue(out["work_detected"])
        self.assert_telemetry(probe, work_detected=True, work_classes=["dispatch"])

    def test_queued_execution_without_active_queued_run_is_observable_but_not_dispatched(self):
        probe = StubProbe(tasks=[{"id": "t1", "status": "queued_execution"}])
        out = probe.probe()
        self.assertEqual(out["queue_diagnostics"]["queued_execution_tasks"], 1)
        self.assertEqual(out["queue_diagnostics"]["queued_execution_without_queued_run"], 1)
        self.assertFalse(out["dispatch_work"])
        self.assertFalse(out["work_detected"])

    def test_queued_execution_with_queued_run_is_not_reported_as_orphan(self):
        probe = StubProbe(
            tasks=[{"id": "t1", "status": "queued_execution"}],
            runs=[{"id": "r1", "task_id": "t1", "status": "queued", "execution_route": "direct"}],
        )
        out = probe.probe()
        self.assertEqual(out["queue_diagnostics"]["queued_execution_without_queued_run"], 0)

    def test_planning_only_portfolio_candidate_does_not_wake_dispatch(self):
        probe = StubProbe(
            tasks=[{"id": "t1", "status": "queued"}],
            portfolio_candidates=[{"project_key": "demo"}],
        )
        out = probe.probe()
        self.assertFalse(out["dispatch_work"])
        self.assertFalse(out["work_detected"])
        self.assertEqual(out["queue_diagnostics"]["queued_without_product_run"], 1)
        self.assert_telemetry(probe, work_detected=False, work_classes=[])

    def test_queued_tasks_are_classified_by_portfolio_project_eligibility(self):
        probe = StubProbe(
            tasks=[
                {"id": "t1", "status": "queued", "project_id": "p1"},
                {"id": "t2", "status": "queued", "project_id": "p2"},
            ],
            portfolio_candidates=[{"project_id": "p1", "project_key": "demo"}],
        )
        out = probe.probe()
        self.assertEqual(out["queue_diagnostics"]["queued_without_product_run"], 2)
        self.assertEqual(out["queue_diagnostics"]["queued_without_product_run_but_portfolio_eligible"], 1)
        self.assertEqual(out["queue_diagnostics"]["queued_without_product_run_and_not_portfolio_eligible"], 1)
        self.assertFalse(out["dispatch_work"])

    def test_no_portfolio_candidates_keeps_orphan_queue_idle(self):
        out = StubProbe(tasks=[{"id": "t1", "status": "queued"}]).probe()
        self.assertFalse(out["dispatch_work"])

    def test_portfolio_failure_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "portfolio unavailable"):
            StubProbe(portfolio_error=RuntimeError("portfolio unavailable")).probe()

    def test_quota_blocked_preview_is_counted_without_retry(self):
        out = StubProbe(runs=[{"id": "p1", "status": "preview_ready", "candidate_commit":"sha"}], deployments=[{"run_id": "p1", "metadata":{"candidate_commit":"sha"}}]).probe()
        self.assertFalse(out["preview_work"])
        self.assertEqual(out["queue_diagnostics"]["preview_ready_runs"], 1)
        self.assertEqual(out["queue_diagnostics"]["preview_quota_blocked_runs"], 1)

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

    def test_recent_quota_block_suppresses_preview_retry(self):
        probe=StubProbe(
            runs=[{"id":"r-preview","status":"preview_ready","candidate_commit":"sha"}],
            deployments=[{"run_id":"r-preview","metadata":{"candidate_commit":"sha"}}],
        )
        out=probe.probe()
        self.assertFalse(out["preview_work"])
        self.assertFalse(out["work_detected"])

    def test_preview_without_recent_quota_block_remains_actionable(self):
        out=StubProbe(runs=[{"id":"r-preview","status":"preview_ready"}],deployments=[]).probe()
        self.assertTrue(out["preview_work"])


    def test_manual_audit_does_not_wake_preview(self):
        out=StubProbe(runs=[{"id":"audit","status":"preview_ready","metadata":{"source":"dogfood_manual_audit"}}]).probe()
        self.assertFalse(out["preview_work"])
        self.assertFalse(out["work_detected"])
        self.assertEqual(out["queue_diagnostics"]["preview_manual_audit_only_runs"],1)

    def test_quota_for_old_sha_keeps_new_sha_actionable(self):
        out=StubProbe(
            runs=[{"id":"r","status":"preview_ready","candidate_commit":"new"}],
            deployments=[{"run_id":"r","metadata":{"candidate_commit":"old"}}]
        ).probe()
        self.assertTrue(out["preview_work"])
        self.assertEqual(out["queue_diagnostics"]["preview_quota_blocked_runs"],0)

    def test_individual_work_signals_record_normalized_work_classes(self):
        cases = {
            "github_access": {"github_access": [{"project_id": "p1"}]},
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
                "payload": {"work_detected": True, "work_classes": ["product"], "queue_diagnostics": out["queue_diagnostics"]},
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
