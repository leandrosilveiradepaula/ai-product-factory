"""Adversarial offline tests for an opt-in external scheduler. Zero real HTTP."""
from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ai_product_factory.independent_scheduler_watchdog import (
    API, BRANCH, REPOSITORY, REPOSITORY_ID, WORKFLOW, WORKFLOW_PATH,
    WatchdogError, decide, main, run,
)

NOW = datetime(2026, 10, 29, 15, 30, tzinfo=timezone.utc)


def when(delta: timedelta) -> str:
    return (NOW - delta).isoformat().replace("+00:00", "Z")


def workflow_run(ident: int, delta: timedelta, *, event: str = "schedule",
                 conclusion: str = "success", status: str = "completed") -> dict:
    return {
        "id": ident, "event": event, "created_at": when(delta),
        "path": WORKFLOW_PATH, "head_branch": BRANCH,
        "head_sha": "a" * 40, "repository": {"full_name": REPOSITORY},
        "status": status, "conclusion": conclusion,
    }


QUEUE_KEYS = (
    "github_access_work", "product_work", "dispatch_work", "integration_work",
    "ci_work", "specialist_work", "preview_work", "release_work", "codex_manual_work",
)


def queue_snapshot(**overrides):
    result = {name: False for name in QUEUE_KEYS}
    result.update(overrides)
    result["work_detected"] = any(result.values())
    result["queue_diagnostics"] = {
        "queue_signal_source": "authoritative_rpc",
        "run_status_partitions_at_limit": [],
        "task_status_partitions_at_limit": [],
        "linked_task_lookup_truncated": 0,
    }
    return result


ACTIVE = lambda: queue_snapshot(dispatch_work=True)
IDLE = lambda: queue_snapshot()


class Response:
    def __init__(self, status, data):
        self.status = status
        self.data = json.dumps(data).encode() if isinstance(data, (list, dict)) else data

    def read(self, limit):
        return self.data[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class GitHubFixture:
    def __init__(self, *, natives=None, dispatches=None, app_wakes=None):
        self.natives = natives if natives is not None else [
            workflow_run(101, timedelta(minutes=10)),
            workflow_run(100, timedelta(minutes=40)),
        ]
        self.dispatches = dispatches if dispatches is not None else []
        self.app_wakes = app_wakes if app_wakes is not None else []
        self.calls = []
        self.fail_on = None
        self.repo_id = REPOSITORY_ID
        self.probe_conclusions = {row["id"]: "success" for row in self.natives}

    def open(self, request, timeout):
        self.calls.append(request)
        path = request.full_url.removeprefix("https://api.github.com")
        if path == self.fail_on:
            raise RuntimeError("very_secret_DO_NOT_LOG")
        if path == "/repos/" + REPOSITORY:
            return Response(200, {"id": self.repo_id, "full_name": REPOSITORY, "default_branch": BRANCH})
        if path == "/repos/" + REPOSITORY + "/actions/workflows/" + WORKFLOW:
            return Response(200, {"id": 789, "path": WORKFLOW_PATH, "state": "active"})
        if path.endswith("runs?event=schedule&branch=main&per_page=20"):
            return Response(200, {"total_count": len(self.natives), "workflow_runs": self.natives})
        if path.endswith("runs?event=workflow_dispatch&branch=main&per_page=20"):
            return Response(200, {"total_count": len(self.dispatches), "workflow_runs": self.dispatches})
        if path.endswith("runs?event=repository_dispatch&branch=main&per_page=20"):
            return Response(200, {"total_count": len(self.app_wakes), "workflow_runs": self.app_wakes})
        if "/jobs?per_page=100" in path:
            ident = int(path.split("/actions/runs/")[1].split("/jobs")[0])
            return Response(200, {"total_count": 1, "jobs": [{
                "id": ident + 1000, "run_id": ident, "head_sha": "a" * 40,
                "name": "schedule-probe", "status": "completed",
                "conclusion": self.probe_conclusions.get(ident, "failure"),
            }]})
        if path.endswith("/dispatches"):
            assert request.get_method() == "POST"
            assert json.loads(request.data) == {"ref": "main"}
            return Response(204, b"")
        raise AssertionError("unplanned API path: " + path)

    def has_post(self):
        return any(req.get_method() == "POST" for req in self.calls)


class IndependentSchedulerTests(unittest.TestCase):
    def test_healthy_native_cron_requires_two_real_passed_jobs(self):
        github = GitHubFixture()
        result = run(token="test_token", execute=True, enabled=True, now=NOW, opener=github.open, queue_probe=ACTIVE)
        self.assertEqual(result, {"status": "skipped", "reason_code": "native_healthy"})
        self.assertFalse(github.has_post())

    def test_no_native_cron_dry_run_is_read_only(self):
        github = GitHubFixture(natives=[])
        result = run(token="test_token", execute=False, enabled=False, now=NOW, opener=github.open, queue_probe=ACTIVE)
        self.assertEqual(result, {"status": "would_dispatch", "reason_code": "stalled_actionable_queue"})
        self.assertFalse(github.has_post())

    def test_real_gap_dispatches_only_exact_main_workflow(self):
        github = GitHubFixture(natives=[workflow_run(101, timedelta(hours=5)), workflow_run(100, timedelta(hours=6))])
        result = run(token="test_token", execute=True, enabled=True, now=NOW, opener=github.open, queue_probe=ACTIVE)
        self.assertEqual(result["status"], "dispatch_accepted")
        posts = [r for r in github.calls if r.get_method() == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].full_url, API + "/actions/workflows/" + WORKFLOW + "/dispatches")
        self.assertEqual(json.loads(posts[0].data), {"ref": "main"})
        self.assertEqual(posts[0].get_header("Authorization"), "Bearer test_token")
        self.assertNotIn("token", json.dumps(result))

    def test_disabled_and_missing_credential_do_not_even_read_github(self):
        github = GitHubFixture(natives=[])
        self.assertEqual(run(token="test_token", execute=True, enabled=False,
                             now=NOW, opener=github.open, queue_probe=ACTIVE)["reason_code"], "explicit_activation_required")
        self.assertEqual(run(token="", execute=True, enabled=True,
                             now=NOW, opener=github.open, queue_probe=ACTIVE)["reason_code"], "github_credential_unavailable")
        self.assertEqual(github.calls, [])

    def test_recent_manual_wake_suppresses_duplicate_dispatch(self):
        github = GitHubFixture(natives=[], dispatches=[
            workflow_run(88, timedelta(minutes=12), event="workflow_dispatch")])
        self.assertEqual(run(token="secret", execute=True, enabled=True,
                             now=NOW, opener=github.open, queue_probe=ACTIVE)["reason_code"], "recent_dispatch")
        self.assertFalse(github.has_post())

    def test_old_manual_dispatch_does_not_mask_persistent_gap(self):
        github = GitHubFixture(natives=[], dispatches=[
            workflow_run(88, timedelta(minutes=42), event="workflow_dispatch")])
        self.assertEqual(run(token="secret", execute=False, enabled=False,
                             now=NOW, opener=github.open, queue_probe=ACTIVE)["status"], "would_dispatch")

    def test_one_recent_native_after_hours_outage_is_not_recovery(self):
        github = GitHubFixture(natives=[workflow_run(101, timedelta(minutes=12))])
        self.assertEqual(run(token="secret", execute=False, enabled=False,
                             now=NOW, opener=github.open, queue_probe=ACTIVE)["status"], "would_dispatch")

    def test_recent_native_in_progress_may_finish_before_external_wake(self):
        github = GitHubFixture(natives=[workflow_run(101, timedelta(minutes=4),
                                                    status="in_progress", conclusion="")])
        self.assertEqual(run(token="secret", execute=True, enabled=True,
                             now=NOW, opener=github.open, queue_probe=ACTIVE)["reason_code"], "native_in_progress")
        self.assertFalse(github.has_post())

    def test_failed_native_probe_never_proves_healthy(self):
        github = GitHubFixture()
        github.probe_conclusions[101] = "failure"
        self.assertEqual(run(token="secret", execute=False, enabled=False,
                             now=NOW, opener=github.open, queue_probe=ACTIVE)["status"], "would_dispatch")

    def test_wrong_repo_identity_fails_closed(self):
        github = GitHubFixture(natives=[])
        github.repo_id = 12345
        with self.assertRaisesRegex(WatchdogError, "target_identity"):
            run(token="secret", execute=True, enabled=True, now=NOW, opener=github.open, queue_probe=ACTIVE)
        self.assertFalse(github.has_post())

    def test_foreign_workflow_event_fails_closed(self):
        github = GitHubFixture(natives=[workflow_run(101, timedelta(hours=3))])
        github.natives[0]["event"] = "workflow_dispatch"
        with self.assertRaisesRegex(WatchdogError, "untrusted_workflow"):
            run(token="secret", execute=True, enabled=True, now=NOW, opener=github.open, queue_probe=ACTIVE)
        self.assertFalse(github.has_post())

    def test_unsorted_or_future_runs_fail_closed(self):
        for natives in (
            [workflow_run(100, timedelta(hours=3)), workflow_run(101, timedelta(hours=2))],
            [workflow_run(101, timedelta(minutes=-10))],
        ):
            github = GitHubFixture(natives=natives)
            with self.assertRaises(WatchdogError):
                run(token="secret", execute=True, enabled=True, now=NOW, opener=github.open, queue_probe=ACTIVE)
            self.assertFalse(github.has_post())

    def test_undelivered_api_never_leaks_secret(self):
        github = GitHubFixture(natives=[])
        github.fail_on = "/repos/" + REPOSITORY
        with self.assertRaisesRegex(WatchdogError, "github_api_unavailable"):
            run(token="very_secret_DO_NOT_LOG", execute=True, enabled=True,
                now=NOW, opener=github.open, queue_probe=ACTIVE)
        out = io.StringIO()
        with patch.dict(os.environ, {
            "FACTORY_EXTERNAL_GITHUB_TOKEN": "very_secret_DO_NOT_LOG",
            "FACTORY_EXTERNAL_SCHEDULER_ENABLED": "true",
        }), patch("urllib.request.urlopen", side_effect=RuntimeError("very_secret_DO_NOT_LOG")), contextlib.redirect_stdout(out):
            self.assertEqual(main(["--execute"]), 2)
        self.assertNotIn("very_secret_DO_NOT_LOG", out.getvalue())
        self.assertIn('"status": "blocked"', out.getvalue())

    def test_main_defaults_to_check_and_never_posts(self):
        github = GitHubFixture(natives=[])
        out = io.StringIO()
        with patch.dict(os.environ, {
            "FACTORY_EXTERNAL_GITHUB_TOKEN": "demo",
            "FACTORY_EXTERNAL_SCHEDULER_ENABLED": "true",
        }), patch("urllib.request.urlopen", side_effect=github.open), patch("ai_product_factory.independent_scheduler_watchdog._trusted_control_plane_probe", return_value=ACTIVE), contextlib.redirect_stdout(out):
            self.assertEqual(main([]), 0)
        self.assertIn('"status": "would_dispatch"', out.getvalue())
        self.assertFalse(github.has_post())

    def test_missing_queue_proof_blocks_recovery_even_with_five_hour_cron_gap(self):
        github = GitHubFixture(natives=[])
        with self.assertRaisesRegex(WatchdogError, "control_plane_evidence_unavailable"):
            run(token="secret", execute=True, enabled=True, now=NOW,
                opener=github.open, queue_probe=None)
        self.assertFalse(github.has_post())

    def test_healthy_cron_skips_before_asking_for_sensitive_control_plane_access(self):
        github = GitHubFixture()
        result = run(token="secret", execute=True, enabled=True, now=NOW,
                     opener=github.open, queue_probe=lambda: (_ for _ in ()).throw(AssertionError()))
        self.assertEqual(result["reason_code"], "native_healthy")
        self.assertFalse(github.has_post())

    def test_stale_cron_but_empty_authoritative_queue_never_dispatches(self):
        github = GitHubFixture(natives=[])
        result = run(token="secret", execute=True, enabled=True,
                     now=NOW, opener=github.open, queue_probe=IDLE)
        self.assertEqual(result, {"status": "skipped", "reason_code": "no_actionable_work"})
        self.assertFalse(github.has_post())

    def test_github_access_alone_is_not_a_work_recovery_signal(self):
        github = GitHubFixture(natives=[])
        result = run(token="secret", execute=True, enabled=True,
                     now=NOW, opener=github.open,
                     queue_probe=lambda: queue_snapshot(github_access_work=True))
        self.assertEqual(result["reason_code"], "no_actionable_work")
        self.assertFalse(github.has_post())

    def test_truncated_queue_diagnostics_fail_closed(self):
        for diagnostics in (
            {"run_status_partitions_at_limit": ["preview_ready"]},
            {"task_status_partitions_at_limit": ["queued_execution"]},
            {"linked_task_lookup_truncated": 1},
            {"queue_signal_source": "unverified_summary"},
        ):
            snapshot = queue_snapshot(preview_work=True)
            snapshot["queue_diagnostics"].update(diagnostics)
            github = GitHubFixture(natives=[])
            with self.assertRaisesRegex(WatchdogError, "incomplete_control_plane_queue_evidence"):
                run(token="secret", execute=True, enabled=True, now=NOW,
                    opener=github.open, queue_probe=lambda: snapshot)
            self.assertFalse(github.has_post())

    def test_preview_only_is_eligible_after_actual_read_only_probe(self):
        github = GitHubFixture(natives=[])
        result = run(token="secret", execute=False, enabled=False,
                     now=NOW, opener=github.open,
                     queue_probe=lambda: queue_snapshot(preview_work=True))
        self.assertEqual(result["status"], "would_dispatch")
        self.assertFalse(github.has_post())

    def test_recent_github_app_wake_prevents_double_dispatch(self):
        github = GitHubFixture(natives=[], app_wakes=[workflow_run(
            88, timedelta(minutes=5), event="repository_dispatch")])
        result = run(token="secret", execute=True, enabled=True, now=NOW,
                     opener=github.open, queue_probe=ACTIVE)
        self.assertEqual(result["reason_code"], "recent_dispatch")
        self.assertFalse(github.has_post())

    def test_incomplete_or_contradictory_control_plane_proof_blocks(self):
        for probe in (lambda: {"work_detected": True},
                      lambda: {**queue_snapshot(), "work_detected": True},
                      lambda: {**queue_snapshot(dispatch_work=True), "preview_work": 1},
                      lambda: ["work"],
                      lambda: (_ for _ in ()).throw(RuntimeError("PRIVATE_KEY"))):
            github = GitHubFixture(natives=[])
            with self.subTest(probe=probe), self.assertRaises(WatchdogError):
                run(token="secret", execute=True, enabled=True,
                    now=NOW, opener=github.open, queue_probe=probe)
            self.assertFalse(github.has_post())

    def test_external_control_plane_identity_and_auth_are_not_guessed(self):
        from ai_product_factory.independent_scheduler_watchdog import (
            _trusted_control_plane_probe, CONTROL_PLANE_URL,
        )
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(_trusted_control_plane_probe())
        with patch.dict(os.environ, {
            "FACTORY_EXTERNAL_CONTROL_PLANE_URL": "https://attacker.example",
            "FACTORY_EXTERNAL_CONTROL_PLANE_KEY": "super_secret",
        }, clear=True):
            with self.assertRaisesRegex(WatchdogError, "identity_mismatch"):
                _trusted_control_plane_probe()
        with patch.dict(os.environ, {
            "FACTORY_EXTERNAL_CONTROL_PLANE_URL": CONTROL_PLANE_URL,
            "FACTORY_EXTERNAL_CONTROL_PLANE_KEY": "valid_scoped_key",
        }, clear=True):
            self.assertTrue(callable(_trusted_control_plane_probe()))

    def test_bad_control_plane_key_stays_redacted_in_main(self):
        out = io.StringIO()
        with patch.dict(os.environ, {
            "FACTORY_EXTERNAL_GITHUB_TOKEN": "gh_secret",
            "FACTORY_EXTERNAL_CONTROL_PLANE_URL": "https://attacker.example",
            "FACTORY_EXTERNAL_CONTROL_PLANE_KEY": "database_very_secret",
            "FACTORY_EXTERNAL_SCHEDULER_ENABLED": "true",
        }, clear=True), contextlib.redirect_stdout(out):
            self.assertEqual(main(["--execute"]), 2)
        self.assertNotIn("database_very_secret", out.getvalue())
        self.assertNotIn("gh_secret", out.getvalue())
        self.assertIn('"status": "blocked"', out.getvalue())

    def test_repository_and_dispatch_contract_are_immutable(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        source = (root / "src/ai_product_factory/independent_scheduler_watchdog.py").read_text()
        self.assertIn('REPOSITORY = "leandrosilveiradepaula/ai-product-factory"', source)
        self.assertIn('WORKFLOW = "autonomous-runner.yml"', source)
        self.assertNotIn("pulls/", source)
        self.assertNotIn("merge_pull_request", source)
        self.assertNotIn("FACTORY_PRIMARY_MODEL_ENABLED", source)


if __name__ == "__main__":
    unittest.main()