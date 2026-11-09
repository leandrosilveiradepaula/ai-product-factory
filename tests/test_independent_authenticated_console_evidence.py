from __future__ import annotations

import unittest

from ai_product_factory.independent_authenticated_console_evidence import (
    AuthenticatedConsoleEvidenceBlocked, HISTORICAL_SOURCE_SHA,
    HISTORICAL_WORKFLOW_RUN_ID, verify_authenticated_console_evidence,
    verify_reusable_historical_authenticated_console_evidence,
)


REPO = "leandrosilveiradepaula/ai-product-factory"
SHA = "a" * 40
RUN = 42439592059


def fixture():
    prefix = "/repos/" + REPO
    return {
        prefix: {"full_name": REPO, "default_branch": "main"},
        prefix + "/git/ref/heads/main": {"object": {"sha": SHA}},
        prefix + "/actions/runs/" + str(RUN): {
            "id": RUN, "name": "Authenticated Console visual evidence",
            "path": ".github/workflows/authenticated-visual-evidence.yml",
            "event": "workflow_dispatch", "head_branch": "main", "head_sha": SHA,
            "run_attempt": 1, "status": "completed", "conclusion": "success",
            "repository": {"full_name": REPO},
        },
        prefix + "/actions/runs/" + str(RUN) + "/jobs?per_page=100": {
            "total_count": 1, "jobs": [{"name": "capture", "run_id": RUN,
                "head_sha": SHA, "status": "completed", "conclusion": "success"}],
        },
        prefix + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100": {
            "total_count": 1, "artifacts": [{"id": 8, "name": "authenticated-console-" + str(RUN),
                "expired": False, "size_in_bytes": 1,
                "workflow_run": {"id": RUN, "head_sha": SHA, "head_branch": "main"}}],
        },
    }


class AuthenticatedConsoleEvidenceTests(unittest.TestCase):
    def verify(self, data=None):
        data = fixture() if data is None else data
        return verify_authenticated_console_evidence(
            repository=REPO, assessed_commit=SHA, workflow_run_id=RUN,
            github_get=lambda path: data[path],
        )

    def test_exact_manual_browser_receipt_is_bounded_partial_evidence(self):
        proof = self.verify()
        self.assertEqual(proof.evidence, ("https://github.com/" + REPO + "/actions/runs/" + str(RUN) + "#sha=" + SHA,))
        self.assertEqual(proof.receipt()["does_not_certify"], [
            "authn_authz", "data_access_boundaries", "critical_e2e", "states",
            "critical_journeys", "product_ready",
        ])
        self.assertTrue(proof.receipt()["artifact_encrypted_not_read"])

    def test_wrong_identity_artifact_or_rerun_fails_closed(self):
        for path, update in (
            ("run", {"run_attempt": 2}), ("run", {"event": "push"}),
            ("artifact", {"expired": True}), ("artifact", {"head_sha": "b" * 40}),
            ("head", {"sha": "b" * 40}),
        ):
            data = fixture()
            prefix = "/repos/" + REPO
            if path == "run": data[prefix + "/actions/runs/" + str(RUN)].update(update)
            elif path == "artifact":
                artifact = data[prefix + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100"]["artifacts"][0]
                if "expired" in update:
                    artifact.update(update)
                else:
                    artifact["workflow_run"].update(update)
            else: data[prefix + "/git/ref/heads/main"]["object"].update(update)
            with self.subTest(path=path, update=update), self.assertRaises(AuthenticatedConsoleEvidenceBlocked):
                self.verify(data)

    def test_expired_historical_capture_requires_registry_ancestry_and_identical_console(self):
        candidate = "b" * 40
        prefix = "/repos/" + REPO
        tree = {"truncated": False, "tree": [{"type": "blob", "path": "apps/console/app/page.tsx",
                                                 "mode": "100644", "sha": "c" * 40}]}
        data = {
            prefix: {"full_name": REPO, "default_branch": "main"},
            prefix + "/git/ref/heads/main": {"object": {"sha": candidate}},
            prefix + "/actions/runs/" + str(HISTORICAL_WORKFLOW_RUN_ID): {
                "id": HISTORICAL_WORKFLOW_RUN_ID, "name": "Authenticated Console visual evidence",
                "path": ".github/workflows/authenticated-visual-evidence.yml", "event": "workflow_dispatch",
                "head_branch": "main", "head_sha": HISTORICAL_SOURCE_SHA, "run_attempt": 1,
                "status": "completed", "conclusion": "success", "repository": {"full_name": REPO},
            },
            prefix + "/actions/runs/" + str(HISTORICAL_WORKFLOW_RUN_ID) + "/jobs?per_page=100": {
                "total_count": 1, "jobs": [{"name": "capture", "run_id": HISTORICAL_WORKFLOW_RUN_ID,
                "head_sha": HISTORICAL_SOURCE_SHA, "status": "completed", "conclusion": "success"}]},
            prefix + "/actions/runs/" + str(HISTORICAL_WORKFLOW_RUN_ID) + "/artifacts?per_page=100": {
                "total_count": 0, "artifacts": []},
            prefix + "/compare/" + HISTORICAL_SOURCE_SHA + "..." + candidate: {
                "status": "ahead", "behind_by": 0, "base_commit": {"sha": HISTORICAL_SOURCE_SHA},
                "merge_base_commit": {"sha": HISTORICAL_SOURCE_SHA}},
            prefix + "/git/trees/" + HISTORICAL_SOURCE_SHA + "?recursive=1": tree,
            prefix + "/git/trees/" + candidate + "?recursive=1": tree,
        }
        registry = [{"workflow_run_id": HISTORICAL_WORKFLOW_RUN_ID,
                     "source_commit": HISTORICAL_SOURCE_SHA,
                     "artifact_name": "authenticated-console-" + str(HISTORICAL_WORKFLOW_RUN_ID),
                     "status": "captured"}]
        proof = verify_reusable_historical_authenticated_console_evidence(
            repository=REPO, assessed_commit=candidate, github_get=lambda path: data[path],
            control_plane_get=lambda path: registry,
        )
        self.assertIsNone(proof.artifact_id)
        self.assertFalse(proof.receipt()["artifact_available"])
        data[prefix + "/git/trees/" + candidate + "?recursive=1"] = {
            "truncated": False, "tree": []}
        with self.assertRaises(AuthenticatedConsoleEvidenceBlocked):
            verify_reusable_historical_authenticated_console_evidence(
                repository=REPO, assessed_commit=candidate, github_get=lambda path: data[path],
                control_plane_get=lambda path: registry,
            )
