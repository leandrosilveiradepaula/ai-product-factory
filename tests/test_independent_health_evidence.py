"""Executed verifier contracts: exact SHA, provider, live endpoint and scheduler."""
from __future__ import annotations

import copy
import json
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ai_product_factory.independent_health_evidence import (
    REPO, HEALTH_URL, TRUSTED_WORKFLOW, HealthEvidenceBlocked,
    verify_operational_health, verify_health_for_certification,
    verify_vercel_provider_status, verify_control_plane, verify_probes,
)

HEAD = "b" * 40
DEPLOYED = "a" * 40
NOW = datetime(2026, 11, 5, 13, 15, tzinfo=timezone.utc)
PROJECT = "00000000-0000-4000-8000-000000000001"
CRM = "00000000-0000-4000-8000-000000000002"
VERCEL_URL = (
    "https://vercel.com/leandros-projects-102e32ab/"
    "ai-product-factory-console/GvUP7XvtKY9hL9ab6xLQJD8KR3zh"
)


def data():
    return {
        "ref": {"object": {"sha": HEAD}},
        "commit": {"sha": DEPLOYED},
        "provider": {
            "statuses": [
                {"context": "Vercel", "state": "success",
                 "description": "Deployment has completed",
                 "target_url": VERCEL_URL,
                 "avatar_url": "https://avatars.githubusercontent.com/in/8329?v=4"}
            ],
        },
        "compare": {"status": "ahead", "behind_by": 0,
                    "total_commits": 4,
                    "merge_base_commit": {"sha": DEPLOYED},
                    "files": [{"filename": "src/ai_product_factory/audit.py"}]},
        "health": {"status": "ok", "service": "ai-product-factory-console",
                   "commit": DEPLOYED[:12]},
        "events": [
            {"event_type": "schedule_probe.observed",
             "actor_type": "system", "actor_ref": "schedule-probe",
             "created_at": (NOW - timedelta(minutes=m)).isoformat(),
             "payload": {"work_detected": False, "queue_diagnostics": {
                "queue_signal_source": "authoritative_rpc",
                "queued_tasks": 0, "queued_execution_tasks": 0,
                "eligible_product_tasks": 0,
                "stale_integration_change_sets": 0,
                "queued_execution_without_queued_run": 0,
            }}}
            for m in (4, 19, 34)
        ],
        "projects": [
            {"id": PROJECT, "project_key": "ai-product-factory", "is_active": True},
            {"id": CRM, "project_key": "crm-infodive", "is_active": True},
        ],
        "controls": [
            {"project_id": PROJECT, "state": "running", "generation": 1},
            {"project_id": CRM, "state": "stopped", "generation": 19},
        ],
    }


class Sources:
    def __init__(self, values):
        self.values = values
        self.github_calls = []
        self.cp_calls = []

    def github(self, path):
        self.github_calls.append(path)
        if path.endswith("/git/ref/heads/main"):
            return copy.deepcopy(self.values["ref"])
        if re.fullmatch(r"/repos/" + re.escape(REPO) + r"/commits/[0-9a-f]{12}", path):
            return copy.deepcopy(self.values["commit"])
        if path.endswith("/commits/" + DEPLOYED + "/status"):
            return copy.deepcopy(self.values["provider"])
        if "/compare/" in path:
            return copy.deepcopy(self.values["compare"])
        raise AssertionError("unapproved GitHub GET path: " + path)

    def cp(self, route):
        self.cp_calls.append(route)
        if route.startswith("factory_audit_events?"):
            return copy.deepcopy(self.values["events"])
        if route.startswith("factory_projects?"):
            return copy.deepcopy(self.values["projects"])
        if route.startswith("factory_project_execution_controls?"):
            return copy.deepcopy(self.values["controls"])
        raise AssertionError("unapproved CP GET: " + route)

    def console(self, url):
        assert url == HEALTH_URL
        return (200, {"content-type": "application/json; charset=utf-8"},
                json.dumps(self.values["health"]).encode())

    def verify(self):
        return verify_operational_health(
            repository=REPO, assessed_commit=HEAD, github_get=self.github,
            cp_get=self.cp, console_get=self.console, now=NOW,
        )


class IndependentHealthTests(unittest.TestCase):
    def test_success_is_scoped_and_read_only(self):
        s = Sources(data())
        proof = s.verify()
        self.assertEqual(proof.deployed_commit, DEPLOYED)
        self.assertEqual(proof.active_projects, 2)
        self.assertEqual(proof.assessed_commit, HEAD)
        self.assertFalse(proof.product_ready)
        self.assertFalse(proof.production_released)
        self.assertEqual(proof.writes, 0)
        self.assertEqual(proof.paid_calls, 0)
        self.assertEqual(len([p for p in s.github_calls
                              if p.endswith("/git/ref/heads/main")]), 2)
        self.assertEqual(len(s.cp_calls), 3)
        self.assertTrue(all("/rpc/" not in route for route in s.cp_calls))

    def test_github_main_and_console_are_exactly_bound(self):
        for mutation in (
            lambda d: d["ref"]["object"].update(sha="c" * 40),
            lambda d: d["commit"].update(sha="d" * 40),
            lambda d: d["compare"].update(status="behind"),
            lambda d: d["compare"].update(behind_by=1),
            lambda d: d["compare"]["merge_base_commit"].update(sha="d" * 40),
            lambda d: d["compare"]["files"].append({"filename": "apps/console/app/page.tsx"}),
            lambda d: d["health"].update(commit="f" * 12),
            lambda d: d["health"].update(status="not_ready"),
            lambda d: d["health"].update(service="attacker"),
        ):
            d = data()
            mutation(d)
            with self.subTest(mutation=repr(mutation)), self.assertRaises(HealthEvidenceBlocked):
                Sources(d).verify()

    def test_vercel_cancelled_signal_and_wrong_provider_fail_closed(self):
        for mutation in (
            lambda d: d["provider"]["statuses"][0].update(
                description="Canceled by Ignored Build Step"),
            lambda d: d["provider"]["statuses"][0].update(state="failure"),
            lambda d: d["provider"]["statuses"][0].update(
                target_url="https://evil.example/dpl_attack"),
            lambda d: d["provider"]["statuses"][0].update(avatar_url="https://evil.example/icon"),
            lambda d: d["provider"]["statuses"][0].update(context="other"),
            lambda d: d["provider"].update(statuses=[]),
        ):
            d = data()
            mutation(d)
            with self.subTest(mutation=repr(mutation)), self.assertRaises(HealthEvidenceBlocked):
                Sources(d).verify()

    def test_two_latest_scheduler_events_not_old_selected_success(self):
        for mutation in (
            lambda d: d.update(events=d["events"][:1]),
            lambda d: d["events"][1].update(created_at=d["events"][0]["created_at"]),
            lambda d: d["events"][0].update(actor_ref="attacker"),
            lambda d: d["events"][0].update(actor_type="human"),
            lambda d: d["events"][0]["payload"].update(work_detected="false"),
            lambda d: d["events"][0]["payload"]["queue_diagnostics"].update(
                queue_signal_source="fixture"),
            lambda d: d["events"][0]["payload"]["queue_diagnostics"].update(
                stale_integration_change_sets=1),
            lambda d: d["events"][0]["payload"]["queue_diagnostics"].update(
                queued_tasks=1),
            lambda d: d["events"][0].update(
                created_at=(NOW - timedelta(minutes=27)).isoformat()),
        ):
            d = data()
            mutation(d)
            with self.subTest(mutation=repr(mutation)), self.assertRaises(HealthEvidenceBlocked):
                Sources(d).verify()

    def test_control_plane_missing_project_and_counterfeit_identity(self):
        for mutation in (
            lambda d: d["controls"].pop(),
            lambda d: d["controls"][0].update(state="stopped"),
            lambda d: d["controls"][0].update(generation=-1),
            lambda d: d["projects"].pop(0),
            lambda d: d["controls"][1].update(project_id=PROJECT),
        ):
            d = data()
            mutation(d)
            with self.subTest(mutation=repr(mutation)), self.assertRaises(HealthEvidenceBlocked):
                Sources(d).verify()

    def test_wrong_runner_identity_and_live_proof_is_not_release(self):
        s = Sources(data())
        env = {
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPO,
            "GITHUB_WORKFLOW_REF": TRUSTED_WORKFLOW,
            "GITHUB_EVENT_NAME": "workflow_run",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ID": "42029997676",
        }
        proof = verify_health_for_certification(
            repository=REPO, assessed_commit=HEAD,
            github_get=s.github, control_plane_get=s.cp,
            console_get=s.console, now=NOW, environment=env,
        )
        self.assertEqual((proof.domain, proof.criterion),
                         ("observability_operations", "health"))
        self.assertIn(HEAD, proof.evidence[0])
        for field, bad in (
            ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_WORKFLOW_REF", "other"),
            ("GITHUB_EVENT_NAME", "issue_comment"),
            ("GITHUB_REF", "refs/heads/dev"),
        ):
            modified = dict(env, **{field: bad})
            with self.subTest(field=field), self.assertRaises(HealthEvidenceBlocked):
                verify_health_for_certification(
                    repository=REPO, assessed_commit=HEAD,
                    github_get=s.github, control_plane_get=s.cp,
                    console_get=s.console, now=NOW, environment=modified,
                )


if __name__ == "__main__":
    unittest.main()
