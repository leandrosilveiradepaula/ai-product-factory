"""Adversarial source checks for a real, infra-exhausted greenfield candidate.

All sources are simulated exclusively for unit tests. Passing these tests
cannot grant B4 readiness; the production recovery runner independently
fetches live GitHub and Control Plane sources before requesting the SQL RPC.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_product_factory.specialist_infrastructure_recovery import (
    SpecialistInfrastructureRecoveryBlocked, verify_recovery_sources,
)

RUN = "a" * 8 + "-aaaa-aaaa-aaaa-" + "a" * 12
TASK = "b" * 8 + "-bbbb-bbbb-bbbb-" + "b" * 12
PROJECT = "c" * 8 + "-cccc-cccc-cccc-" + "c" * 12
CHANGE = "d" * 8 + "-dddd-dddd-dddd-" + "d" * 12
ORIGINAL = "1" * 40
CANDIDATE = "2" * 40
FACTORY = "3" * 40
REPOSITORY = "leandrosilveiradepaula/dark-channel-studio"


def fixture() -> dict:
    return {
        "run": {
            "id": RUN, "task_id": TASK, "status": "specialist_review_failed",
            "candidate_commit": CANDIDATE, "branch_name": "factory/change-set-0bcc",
            "metadata": {
                "source": "change-set", "execution_generation": 1,
                "change_set_id": CHANGE,
                "specialist_lanes": {
                    "required": True, "roles": ["qa", "security", "operations"],
                    "candidate_commit": CANDIDATE,
                },
            },
        },
        "task": {"id": TASK, "project_id": PROJECT},
        "project": {
            "id": PROJECT, "project_key": "dark-channel-studio",
            "project_kind": "greenfield", "repository": REPOSITORY,
            "is_active": True,
        },
        "control": {"project_id": PROJECT, "state": "running", "generation": 1},
        "change_set": {
            "id": CHANGE, "project_id": PROJECT, "release_run_id": RUN,
            "status": "ci_pending", "candidate_commit": CANDIDATE,
            "lease_owner": None, "lease_expires_at": None,
        },
        "jobs": [
            {
                "role": role, "status": "blocked", "required": True,
                "attempt_count": 3, "candidate_commit": CANDIDATE,
                "lease_owner": None, "lease_expires_at": None,
                "completed_at": "2026-11-14T21:15:00Z",
                "evidence": {"_factory_epoch": 1, "_factory_claim_token": role},
                "findings": [{"code": "specialist_retry_exhausted",
                              "severity": "critical"}],
            }
            for role in ("qa", "security", "operations")
        ],
        "create_pr": [{"metadata": {"pr": 2, "head_sha": ORIGINAL}}],
        "reconcile": [{
            "metadata": {
                "pr_number": 2, "old_sha": ORIGINAL, "new_sha": CANDIDATE,
                "previous_commit": ORIGINAL, "candidate_commit": CANDIDATE,
                "change_set_id": CHANGE, "compare_status": "ahead",
                "repository": REPOSITORY, "ci_sha": CANDIDATE,
                "ci_run_id": 333, "ci_job_id": 444, "ci_conclusion": "success",
            }
        }],
        "factory_branch": {"commit": {"sha": FACTORY}},
        "factory_runs": {"workflow_runs": [{
            "name": "validate", "head_sha": FACTORY,
            "event": "push", "status": "completed", "conclusion": "success",
        }]},
        "pr": {
            "number": 2, "state": "open", "merged": False,
            "head": {"sha": CANDIDATE, "ref": "factory/change-set-0bcc",
                     "repo": {"full_name": REPOSITORY}},
            "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
        },
        "ci": {"head_sha": CANDIDATE, "event": "pull_request",
               "status": "completed", "conclusion": "success"},
        "ci_jobs": {"jobs": [{
            "id": 444, "status": "completed", "conclusion": "success",
        }]},
    }


def readers(data: dict):
    def read(path):
        if path.startswith("factory_runs?"):
            return [data["run"]]
        if path.startswith("factory_tasks?"):
            return [data["task"]]
        if path.startswith("factory_projects?"):
            return [data["project"]]
        if path.startswith("factory_project_execution_controls?"):
            return [data["control"]]
        if path.startswith("factory_change_sets?"):
            return [data["change_set"]]
        if path.startswith("factory_specialist_lane_jobs?"):
            return data["jobs"]
        if path.startswith("factory_tool_usage?"):
            if "operation=eq.reconcile_pr_candidate" in path:
                return data["reconcile"]
            if "operation=eq.create_pr" in path:
                return data["create_pr"]
        raise AssertionError("unexpected Control Plane path")

    def github_get(repository, path):
        if repository == "leandrosilveiradepaula/ai-product-factory":
            if path.endswith("/branches/main"):
                return data["factory_branch"]
            if "/actions/runs?head_sha=" in path:
                return data["factory_runs"]
        if repository == REPOSITORY:
            if path.endswith("/pulls/2"):
                return data["pr"]
            if path.endswith("/actions/runs/333"):
                return data["ci"]
            if path.endswith("/actions/runs/333/jobs?per_page=100"):
                return data["ci_jobs"]
        raise AssertionError("unexpected GitHub target or path")

    return read, github_get


def verify(data: dict):
    read, github_get = readers(data)
    return verify_recovery_sources(
        read=read, github_get=github_get, run_id=RUN,
        candidate_sha=CANDIDATE, factory_sha=FACTORY,
    )


class Tests(unittest.TestCase):

    def assert_blocked(self, mutate, code):
        data = fixture()
        mutate(data)
        with self.assertRaisesRegex(SpecialistInfrastructureRecoveryBlocked, code):
            verify(data)

    def test_real_source_contract_yields_sha_bound_deterministic_receipt(self):
        first = verify(fixture())
        second = verify(fixture())
        self.assertEqual(first.receipt(), second.receipt())
        self.assertEqual(first.evidence_digest, second.evidence_digest)
        self.assertRegex(first.evidence_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(first.receipt()["writes"], 0)
        self.assertEqual(first.receipt()["paid_calls"], 0)
        self.assertEqual(first.candidate_sha, CANDIDATE)
        self.assertEqual(first.factory_sha, FACTORY)
        self.assertEqual(first.execution_generation, 1)
        self.assertEqual(first.pr_number, 2)

    def test_paused_or_stale_generation_denied(self):
        self.assert_blocked(
            lambda d: d["control"].update(state="paused"),
            "source_run_or_epoch_not_recoverable")
        self.assert_blocked(
            lambda d: d["control"].update(generation=2),
            "source_run_or_epoch_not_recoverable")

    def test_status_or_candidate_changed_denied(self):
        self.assert_blocked(
            lambda d: d["run"].update(status="preview_ready"),
            "source_run_or_epoch_not_recoverable")
        self.assert_blocked(
            lambda d: d["change_set"].update(candidate_commit=ORIGINAL),
            "source_run_or_epoch_not_recoverable")
        self.assert_blocked(
            lambda d: d["run"]["metadata"].update(
                specialist_infrastructure_recovery_v1={"already": "used"}),
            "source_run_or_epoch_not_recoverable")

    def test_any_role_failure_or_real_findings_refused(self):
        self.assert_blocked(
            lambda d: d["jobs"][0].update(status="failed"),
            "specialist_jobs_not_only_infrastructure_exhausted")
        self.assert_blocked(
            lambda d: d["jobs"][0].update(findings=[{"code": "sql_injection"}]),
            "specialist_jobs_not_only_infrastructure_exhausted")
        self.assert_blocked(
            lambda d: d["jobs"][0].update(attempt_count=2),
            "specialist_jobs_not_only_infrastructure_exhausted")
        self.assert_blocked(
            lambda d: d["jobs"][0].update(lease_owner="late-claimed-worker"),
            "specialist_jobs_not_only_infrastructure_exhausted")
        self.assert_blocked(
            lambda d: d["jobs"].append(copy.deepcopy(d["jobs"][0])),
            "specialist_jobs_not_only_infrastructure_exhausted")

    def test_durable_original_pr_reconciliation_required(self):
        self.assert_blocked(
            lambda d: d["reconcile"][0]["metadata"].update(pr_number=3),
            "original_candidate_lineage_not_verified")
        self.assert_blocked(
            lambda d: d["reconcile"][0]["metadata"].update(old_sha="5" * 40),
            "original_candidate_lineage_not_verified")
        self.assert_blocked(
            lambda d: d.update(reconcile=[]),
            "original_candidate_lineage_not_verified")

    def test_factory_fix_must_be_merged_and_validate_push_green(self):
        self.assert_blocked(
            lambda d: d["factory_branch"]["commit"].update(sha="f"*40),
            "factory_fix_not_current_main")
        self.assert_blocked(
            lambda d: d["factory_runs"]["workflow_runs"][0].update(
                conclusion="failure"),
            "merged_factory_source_ci_not_verified")
        self.assert_blocked(
            lambda d: d["factory_runs"]["workflow_runs"][0].update(event="pull_request"),
            "merged_factory_source_ci_not_verified")

    def test_pilot_pr_must_be_exact_candidate_with_no_merge(self):
        self.assert_blocked(
            lambda d: d["pr"]["head"].update(sha=ORIGINAL),
            "candidate_pr_exact_sha_or_branch_changed")
        self.assert_blocked(
            lambda d: d["pr"].update(merged=True, state="closed"),
            "candidate_pr_exact_sha_or_branch_changed")
        self.assert_blocked(
            lambda d: d["pr"]["base"].update(ref="release"),
            "candidate_pr_exact_sha_or_branch_changed")

    def test_ci_must_match_reconciled_exact_job_and_sha(self):
        self.assert_blocked(
            lambda d: d["reconcile"][0]["metadata"].update(ci_sha=ORIGINAL),
            "candidate_ci_receipt_invalid")
        self.assert_blocked(
            lambda d: d["ci"].update(head_sha=ORIGINAL),
            "candidate_ci_exact_sha_not_verified")
        self.assert_blocked(
            lambda d: d["ci_jobs"]["jobs"][0].update(conclusion="failure"),
            "candidate_ci_exact_sha_not_verified")

    def test_bad_identity_never_reaches_provider(self):
        read, github_get = readers(fixture())
        with self.assertRaisesRegex(
                SpecialistInfrastructureRecoveryBlocked,"recovery_identity_invalid"):
            verify_recovery_sources(
                read=read, github_get=github_get,
                run_id=RUN, candidate_sha="invalid", factory_sha=FACTORY,
            )


class TrustedOperatorCommandTests(unittest.TestCase):
    """No untrusted owner command may invoke the privileged control-plane RPC."""

    def _event(self, body, *, owner="leandrosilveiradepaula",
               author_association="OWNER", issue_number=713, pr=False):
        event = {
            "action": "created",
            "issue": {"number": issue_number},
            "comment": {
                "author_association": author_association,
                "user": {"login": owner},
                "body": body,
            },
        }
        if pr:
            event["issue"]["pull_request"] = {"url": "https://github.com/example/pull/1"}
        return event

    def _run(self, event, *, actor="leandrosilveiradepaula",
             event_name="issue_comment", execute=True):
        from scripts import recover_specialist_infrastructure_once as command
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            environ = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_REPOSITORY": "leandrosilveiradepaula/ai-product-factory",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_EVENT_NAME": event_name,
                "GITHUB_ACTOR": actor,
                "GITHUB_REPOSITORY_OWNER": "leandrosilveiradepaula",
                "GITHUB_SHA": FACTORY,
                "GITHUB_EVENT_PATH": str(event_path),
                "FACTORY_SPECIALIST_INFRA_EXECUTE": "true" if execute else "false",
            }
            args = ["--run-id", RUN, "--candidate-sha", CANDIDATE]
            if execute:
                args.append("--execute")
            with patch.dict(os.environ, environ, clear=True):
                with patch.object(command, "SupabaseSpecialistLaneQueue") as queue:
                    with patch.object(command, "verify_recovery_sources") as verify_source:
                        if execute:
                            queue.return_value._rpc.return_value = {
                                "run_id": RUN, "requeued": True,
                                "release_authorized": False,
                            }
                            queue.return_value._get.return_value = [
                                {"role": role, "status": "queued", "attempt_count": 0}
                                for role in ("qa", "security", "operations")
                            ]
                        from ai_product_factory.specialist_infrastructure_recovery import RecoverySources
                        verify_source.return_value = RecoverySources(
                            run_id=RUN, candidate_sha=CANDIDATE, factory_sha=FACTORY,
                            execution_generation=1, repository=REPOSITORY,
                            project_key="dark-channel-studio", pr_number=2,
                            ci_run_id=333, evidence_digest="f"*64,
                        )
                        try:
                            result = command.main(args)
                        except SystemExit as exc:
                            result = exc
                        return result, queue.return_value._rpc.call_count, verify_source.call_count

    def test_exact_owner_issue_comment_authorizes_only_bounded_original_requeue(self):
        event = self._event(
            "/factory-specialist-infra-recover " + RUN + " " + CANDIDATE)
        result, writes, source_checks = self._run(event)
        self.assertEqual(result, 0)
        self.assertEqual(writes, 1)
        self.assertEqual(source_checks, 1)

    def test_owner_command_identity_denies_forged_or_wrong_source(self):
        valid = "/factory-specialist-infra-recover " + RUN + " " + CANDIDATE
        cases = (
            (self._event(valid + " extra"), "leandrosilveiradepaula"),
            (self._event(valid, author_association="MEMBER"), "leandrosilveiradepaula"),
            (self._event(valid, owner="untrusted"), "leandrosilveiradepaula"),
            (self._event(valid, issue_number=712), "leandrosilveiradepaula"),
            (self._event(valid, pr=True), "leandrosilveiradepaula"),
            (self._event(valid), "untrusted"),
        )
        for event, actor in cases:
            with self.subTest(event=event, actor=actor):
                result, writes, source_checks = self._run(event, actor=actor)
                self.assertIsInstance(result, SystemExit)
                self.assertEqual(writes, 0)
                self.assertEqual(source_checks, 0)


if __name__ == "__main__":
    unittest.main()
