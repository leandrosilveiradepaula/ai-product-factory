"""Offline adversarial preflight tests: never touch Supabase, Vercel, GitHub or models."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from email.message import Message

from scripts.resume_preview_backend_unavailable import (
    PreviewEnvironmentNotReady, preview_origin, probe_session,
    prepare_recovery, require_github_pr,
)

SHA = "a" * 40
RUN = "11111111-1111-4111-8111-111111111111"
TASK = "22222222-2222-4222-8222-222222222222"
PROJECT = "33333333-3333-4333-8333-333333333333"
CS = "44444444-4444-4444-8444-444444444444"
BRANCH = "factory/change-set-44444444"
REPO = "owner/service-desk"
URL = "https://service-desk-preview-example.vercel.app"
NUMBER = 10


def fixtures():
    records = {
        "factory_runs": [{"id": RUN, "task_id": TASK, "status": "failed",
                          "candidate_commit": SHA, "branch_name": BRANCH,
                          "metadata": {"change_set_id": CS}}],
        "factory_tasks": [{"id": TASK, "project_id": PROJECT, "status": "failed"}],
        "factory_projects": [{"id": PROJECT, "project_key": "service-desk",
                              "repository": REPO, "manifest": {
                                  "preview": {"provider": "vercel", "required": True}}}],
        "factory_change_sets": [{"id": CS, "release_run_id": RUN, "status": "ci_pending",
                                  "candidate_commit": SHA, "integration_branch": BRANCH,
                                  "metadata": {"integration_release_request": {
                                      "pr_number": NUMBER}}}],
        "factory_evaluations": [{"status": "failure", "baseline_ref": URL,
                                 "result": {"detail": "console: 503 | http_503: fetch /api/session",
                                            "preview_url": URL}}],
        "factory_deployments": [{"status": "success",
                                "metadata": {"candidate_commit": SHA,
                                             "preview_url": URL}}],
    }
    pull = {"number": NUMBER, "state": "open", "merged_at": None, "draft": False,
            "head": {"sha": SHA, "ref": BRANCH,
                     "repo": {"full_name": REPO}}}
    statuses = {"sha": SHA, "statuses": [{
        "context": "Vercel", "state": "success",
        "target_url": "https://vercel.com/team-abc/service-desk/1234567890abcdefghij"}]}
    probe = {"kind": "unauthenticated_json_session_probe",
             "url": URL + "/api/session", "http_status": "401",
             "content_type": "application/json",
             "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return records, pull, statuses, probe


def build(records, pull, statuses, probe):
    calls = {"probe": 0, "github": 0, "cp": 0}

    def cp_get(table, params):
        calls["cp"] += 1
        return deepcopy(records.get(table, []))

    def github_get(repo, path):
        calls["github"] += 1
        assert repo == REPO
        return deepcopy(pull if path.startswith("pulls/") else statuses)

    def session_probe(url):
        calls["probe"] += 1
        assert url == URL
        return deepcopy(probe)

    return (lambda: prepare_recovery(
        run_id=RUN, project_key="service-desk",
        cp_get=cp_get, github_get=github_get, session_probe=session_probe)), calls


class PreviewEnvironmentRecoveryPreflightTests(unittest.TestCase):
    def test_valid_read_only_recovery_request_preserves_human_gate(self):
        f = fixtures()
        execute, calls = build(*f)
        row = execute()
        self.assertEqual(row["p_run_id"], RUN)
        self.assertEqual(row["p_pr_number"], NUMBER)
        self.assertEqual(row["p_verified_github"]["head_sha"], SHA)
        self.assertFalse(row["p_verified_github"]["merged"])
        self.assertEqual(row["p_environment_probe"]["url"], URL + "/api/session")
        self.assertEqual(row["p_environment_probe"]["candidate_commit"], SHA)
        self.assertEqual(calls, {"probe": 1, "github": 2, "cp": 6})

    def test_reject_unsafe_origins(self):
        for bad in (
            "http://service-desk-preview-example.vercel.app",
            "https://service-desk-preview-example.vercel.app.evil.test",
            "https://user:token@service-desk-preview-example.vercel.app",
            "https://service-desk-preview-example.vercel.app:444",
            "https://service-desk-preview-example.vercel.app/other",
            "https://service-desk-preview-example.vercel.app?token=leak",
            "https://service-desk-preview-example.vercel.app#frag",
            "https://127.0.0.1", "https://vercel.app", None,
        ):
            with self.subTest(origin=bad):
                with self.assertRaises(PreviewEnvironmentNotReady):
                    preview_origin(bad)
        self.assertEqual(preview_origin(URL + "/"), URL)

    def test_no_probe_before_verifying_exact_run_project_and_github(self):
        edits = [
            lambda r,p,s,h: r["factory_runs"][0].update(status="completed"),
            lambda r,p,s,h: r["factory_runs"][0].update(candidate_commit="f"*40),
            lambda r,p,s,h: r["factory_projects"][0]["manifest"]["preview"].update(required=False),
            lambda r,p,s,h: r["factory_change_sets"][0].update(status="completed"),
            lambda r,p,s,h: r["factory_evaluations"][0]["result"].update(detail="different runtime failure"),
            lambda r,p,s,h: r["factory_deployments"][0]["metadata"].update(candidate_commit="f"*40),
            lambda r,p,s,h: p.update(state="closed"),
            lambda r,p,s,h: p.update(draft=True),
            lambda r,p,s,h: p["head"].update(sha="f"*40),
            lambda r,p,s,h: p["head"]["repo"].update(full_name="attacker/other"),
            lambda r,p,s,h: s.update(sha="f"*40),
            lambda r,p,s,h: s["statuses"][0].update(state="pending"),
            lambda r,p,s,h: s["statuses"][0].update(target_url="https://evil.example.invalid"),
        ]
        for edit in edits:
            f = fixtures()
            edit(*f)
            execute, calls = build(*f)
            with self.subTest(edit=edit):
                with self.assertRaises(PreviewEnvironmentNotReady):
                    execute()
                self.assertEqual(calls["probe"], 0)

    def test_reject_unverified_new_environment_probe(self):
        cases = [
            {"http_status": "503"},
            {"http_status": "302"},
            {"url": "https://evil.test/api/session"},
            {"content_type": "text/html"},
            {"kind": "forged"},
        ]
        for override in cases:
            records,pull,statuses,probe = fixtures()
            probe.update(override)
            execute, calls = build(records,pull,statuses,probe)
            with self.subTest(override=override):
                with self.assertRaises(PreviewEnvironmentNotReady):
                    execute()
                self.assertEqual(calls["probe"], 1)

    def test_pinned_github_url_rejects_spoofed_statuses(self):
        records,pull,statuses,probe=fixtures()
        statuses["statuses"] = [{"context": "Vercel", "state": "success",
            "target_url": "https://vercel.com/other/project/token?secret=1"}]
        with self.assertRaises(PreviewEnvironmentNotReady):
            require_github_pr(pull=pull,statuses=statuses,repository=REPO,
                              branch=BRANCH,candidate=SHA,number=NUMBER)

    def test_raw_http_503_probe_cannot_pass(self):
        headers = Message()
        headers["Content-Type"] = "application/json"
        exc = HTTPError(URL + "/api/session", 503, "Service Unavailable", headers, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            with self.assertRaisesRegex(PreviewEnvironmentNotReady, "still_unverified"):
                probe_session(URL)


if __name__ == "__main__":
    unittest.main()
