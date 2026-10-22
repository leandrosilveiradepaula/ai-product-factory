"""Offline-only regression for signed exact-SHA Preview browser provenance."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import unittest

from ai_product_factory.candidate_browser_proof import (
    FACTORY_REPOSITORY, observe_browser_proof,
)

PROJECT = "70515123-ecbb-4f4b-a38f-75c54250af56"
REPOSITORY = "leandrosilveiradepaula/infodive-service-desk"
SHA = "c7b061c6f18961bd1fdfea51f59e2985bbe8247a"
FACTORY_SHA = "1489291c0ea1d46e0cbe99dfa7648ea3868e482a"
RUN_ID = 39841239361
REQUEST = "4f678198-f1d5-4e80-a88d-1c46f572240b"
URL = "https://crm-infodive-git-preview-hard-e330ec-leandros-projects-102e32ab.vercel.app"
NOW = datetime.now(timezone.utc)


def fixtures():
    stamp = (NOW - timedelta(seconds=1)).isoformat()
    request_url = f"https://github.com/{FACTORY_REPOSITORY}/actions/runs/{RUN_ID}"
    snapshot = {
        "id": "2ebb6fe2-9819-41b1-9133-d9e70e1dfc72",
        "project_id": PROJECT, "run_id": None, "observed_stage": "verification",
        "created_at": stamp, "gaps": [],
        "constraints": {
            "production_merge_authorized": False,
            "product_ready_inferred": False,
            "release_candidate_ready_inferred": False,
        },
        "source_status": {
            "github_target": "verified",
            "vercel_preview": "resolved",
            "browser_visual_validation": "success",
        },
        "evidence": {
            "target_repository": REPOSITORY,
            "candidate_commit": SHA,
            "preview": {
                "url": URL, "status": "browser_verified", "provider": "vercel",
                "browser_verifier_run_id": RUN_ID,
                "browser_verifier_run_url": request_url,
                "verifier_factory_commit": FACTORY_SHA,
                "browser_request_id": REQUEST,
            },
        },
    }
    run = {
        "id": RUN_ID, "name": "Console evidence " + REQUEST,
        "display_title": "Console evidence " + REQUEST,
        "path": ".github/workflows/console-browser-evidence.yml",
        "event": "workflow_dispatch", "run_attempt": 1,
        "head_branch": "main", "head_sha": FACTORY_SHA,
        "status": "completed", "conclusion": "success",
        "html_url": request_url, "repository": {"full_name": FACTORY_REPOSITORY},
        "created_at": (NOW - timedelta(seconds=65)).isoformat(),
        "updated_at": (NOW - timedelta(seconds=24)).isoformat(),
    }
    jobs = {
        "total_count": 1,
        "jobs": [{
            "id": 10, "name": "browser-evidence", "run_id": RUN_ID,
            "head_sha": FACTORY_SHA, "status": "completed", "conclusion": "success",
        }],
    }
    status = {"sha": SHA, "statuses": [
        {"context": "Vercel", "state": "success", "description": "Deployment has completed"}
    ]}
    return {"snapshots": [snapshot], "run": run, "jobs": jobs, "status": status}


def observe(data, *, factory=True):
    calls = []
    prefix = f"/repos/{FACTORY_REPOSITORY}/actions/runs/{RUN_ID}"

    def cp_get(path):
        calls.append(("supabase", "GET", path))
        if not path.startswith("factory_project_state_snapshots?"):
            raise AssertionError("unknown Control Plane read")
        return data["snapshots"]

    def target_get(path):
        calls.append(("target", "GET", path))
        if path != f"/repos/{REPOSITORY}/commits/{SHA}/status":
            raise AssertionError("outside exact candidate")
        return data["status"]

    def factory_get(path):
        calls.append(("factory", "GET", path))
        if path == prefix:
            return data["run"]
        if path == prefix + "/jobs?per_page=100":
            return data["jobs"]
        raise AssertionError("outside exact Factory verifier")

    result = observe_browser_proof(
        project_id=PROJECT, repository=REPOSITORY, candidate_sha=SHA,
        cp_get=cp_get, target_get=target_get,
        factory_get=factory_get if factory else None,
    )
    return result, calls


class CandidateBrowserProofTests(unittest.TestCase):
    def test_success_only_certifies_public_preview_browser_smoke(self):
        result, calls = observe(fixtures())
        self.assertEqual(result["state"], "verified")
        self.assertTrue(result["verified"])
        self.assertEqual(result["verification_scope"], "public_preview_browser_smoke_only")
        self.assertEqual(result["verifier_run_id"], RUN_ID)
        self.assertEqual(result["receipt_id"], fixtures()["snapshots"][0]["id"])
        self.assertEqual(result["preview_url"], URL)
        self.assertEqual([x[0] for x in calls], ["supabase", "factory", "factory", "target"])
        self.assertTrue(all(method == "GET" for _, method, _ in calls))

    def test_provider_status_without_browser_receipt_is_not_proof(self):
        data = fixtures()
        data["snapshots"] = []
        result, calls = observe(data)
        self.assertEqual(result["state"], "no_exact_sha_browser_receipt")
        self.assertFalse(result["verified"])
        self.assertEqual(len(calls), 1)

    def test_foreign_repo_or_old_sha_cannot_be_promoted(self):
        for key, value in (("target_repository", "external/unrelated"),
                           ("candidate_commit", "f" * 40)):
            with self.subTest(key=key):
                data = fixtures()
                data["snapshots"][0]["evidence"][key] = value
                result, calls = observe(data)
                self.assertEqual(result["state"], "no_exact_sha_browser_receipt")
                self.assertEqual(len(calls), 1)

    def test_failed_newer_receipt_cannot_be_overridden_by_older_success(self):
        data = fixtures()
        older = copy.deepcopy(data["snapshots"][0])
        older["created_at"] = (NOW - timedelta(minutes=3)).isoformat()
        newer = copy.deepcopy(data["snapshots"][0])
        newer["id"] = "4bbeeffa-cb52-4e01-9079-f8aa97310fb3"
        newer["created_at"] = NOW.isoformat()
        newer["evidence"]["preview"]["status"] = "browser_failed"
        newer["source_status"]["browser_visual_validation"] = "failure"
        data["snapshots"] = [older, newer]  # Test unsorted REST payload too.
        result, calls = observe(data)
        self.assertEqual(result["state"], "invalid_browser_receipt")
        self.assertEqual(len(calls), 1)

    def test_unrelated_later_receipt_does_not_replace_exact_sha_proof(self):
        data = fixtures()
        other = copy.deepcopy(data["snapshots"][0])
        other["id"] = "4bbeeffa-cb52-4e01-9079-f8aa97310fb3"
        other["created_at"] = NOW.isoformat()
        other["evidence"]["candidate_commit"] = "e" * 40
        data["snapshots"].insert(0, other)
        self.assertTrue(observe(data)[0]["verified"])

    def test_missing_factory_verifier_blocks_even_with_snapshot(self):
        result, calls = observe(fixtures(), factory=False)
        self.assertEqual(result["state"], "browser_verifier_unavailable")
        self.assertEqual(len(calls), 1)

    def test_run_identity_must_be_exact(self):
        deviations = (
            ("path", ".github/workflows/untrusted.yml"),
            ("event", "push"),
            ("head_sha", "f" * 40),
            ("head_branch", "preview/other"),
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("run_attempt", 2),
            ("display_title", "Console evidence different-uuid"),
            ("html_url", "https://example.invalid"),
            ("id", RUN_ID + 1),
        )
        for key, value in deviations:
            with self.subTest(key=key):
                data = fixtures()
                data["run"][key] = value
                self.assertEqual(observe(data)[0]["state"], "browser_verifier_mismatch")

    def test_jobs_must_prove_one_successful_browser_job(self):
        for key, value in (
            ("name", "upload-artifact"),
            ("run_id", RUN_ID + 1),
            ("head_sha", "f" * 40),
            ("conclusion", "failure"),
            ("status", "queued"),
        ):
            with self.subTest(key=key):
                data = fixtures()
                data["jobs"]["jobs"][0][key] = value
                self.assertEqual(observe(data)[0]["state"], "browser_verifier_mismatch")
        data = fixtures()
        data["jobs"]["total_count"] = 2
        self.assertEqual(observe(data)[0]["state"], "browser_verifier_mismatch")

    def test_vercel_latest_failure_or_stale_sha_blocks(self):
        for mutate in (
            lambda d: d["status"]["statuses"][0].update(state="failure"),
            lambda d: d["status"].update(sha="f" * 40),
            lambda d: d["status"].update(statuses=[]),
            lambda d: d["status"].update(statuses=[{"context":"Other","state":"success"}]),
        ):
            data = fixtures()
            mutate(data)
            self.assertEqual(observe(data)[0]["state"], "vercel_ready_not_current")

    def test_invalid_browser_url_or_nonce_or_scoped_identity_blocks(self):
        for mutate in (
            lambda d: d["snapshots"][0]["evidence"]["preview"].update(url="https://evil.example"),
            lambda d: d["snapshots"][0]["evidence"]["preview"].update(browser_request_id="x"),
            lambda d: d["snapshots"][0]["evidence"]["preview"].update(browser_verifier_run_id=0),
            lambda d: d["snapshots"][0]["evidence"]["preview"].update(verifier_factory_commit="z"*40),
            lambda d: d["snapshots"][0]["source_status"].update(github_target="unverified"),
            lambda d: d["snapshots"][0]["constraints"].update(product_ready_inferred=True),
            lambda d: d["snapshots"][0].update(gaps=[{"reason":"not_ready"}]),
        ):
            data = fixtures()
            mutate(data)
            self.assertEqual(observe(data)[0]["state"], "invalid_browser_receipt")

    def test_malformed_or_unbounded_snapshot_inventory_fails_closed(self):
        for rows in (None, {}, ["bad"], fixtures()["snapshots"] * 26):
            data = fixtures()
            data["snapshots"] = rows
            self.assertEqual(observe(data)[0]["state"], "unverifiable_snapshot_inventory")

    def test_expired_and_future_receipts_are_not_authoritative(self):
        for when in (NOW - timedelta(days=15), NOW + timedelta(minutes=15)):
            data = fixtures()
            data["snapshots"][0]["created_at"] = when.isoformat()
            self.assertEqual(observe(data)[0]["state"], "expired_or_future_browser_receipt")

    def test_receipt_written_before_browser_run_completion_is_rejected(self):
        data = fixtures()
        data["run"]["updated_at"] = (NOW + timedelta(hours=1)).isoformat()
        self.assertEqual(observe(data)[0]["state"], "browser_verifier_mismatch")

    def test_untrusted_error_details_are_not_echoed(self):
        data = fixtures()
        data["snapshots"][0]["created_at"] = "secret-token-danger-not-time"
        receipt, _ = observe(data)
        self.assertEqual(receipt["state"], "unverifiable_browser_provenance")
        self.assertNotIn("secret", str(receipt))
        self.assertFalse(receipt["verified"])


if __name__ == "__main__":
    unittest.main()
