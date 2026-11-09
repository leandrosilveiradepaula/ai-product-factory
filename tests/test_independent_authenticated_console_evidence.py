from __future__ import annotations

import unittest

from ai_product_factory.independent_authenticated_console_evidence import (
    AuthenticatedConsoleEvidenceBlocked, verify_authenticated_console_evidence,
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
