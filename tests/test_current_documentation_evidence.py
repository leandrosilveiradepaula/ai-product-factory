"""Current merged PR documentation evidence: positive and adversarial tests."""
from __future__ import annotations

import base64
import copy
import hashlib
import unittest

from ai_product_factory.current_documentation_evidence import (
    CurrentDocumentationBlocked, REPO,
    verify_current_clean_setup, verify_current_isolated_rollback,
)
from tests.test_independent_setup_evidence import receipt_zip
from tests.test_independent_rollback_evidence import archive

SHA = "f" * 40
HEAD = "a" * 40
TREE = "b" * 40
CURRENT = 123
SETUP_RUN = 456
ROLLBACK_RUN = 457


def env():
    return {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPO,
        "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_WORKFLOW_REF": REPO + "/.github/workflows/autonomous-runner.yml@refs/heads/main",
        "GITHUB_RUN_ID": str(CURRENT), "GITHUB_TOKEN": "native-fixture",
    }


def fixture():
    prefix = "/repos/" + REPO
    raw_setup = receipt_zip()
    raw_rollback, _ = archive()
    output = {
        prefix + "/git/ref/heads/main": {"object": {"sha": SHA}},
        prefix + "/actions/runs/" + str(CURRENT): {
            "id": CURRENT, "name": "Factory autonomous runner",
            "path": ".github/workflows/autonomous-runner.yml", "event": "workflow_run",
            "head_sha": SHA, "head_branch": "main", "run_attempt": 1,
        },
        prefix + "/commits/" + SHA: {
            "sha": SHA,
            "commit": {"tree": {"sha": TREE}},
            "parents": [{"sha": "c" * 40}, {"sha": HEAD}],
        },
        prefix + "/commits/" + HEAD: {
            "sha": HEAD, "commit": {"tree": {"sha": TREE}},
        },
        prefix + "/commits/" + HEAD + "/pulls?per_page=100": [{
            "number": 1577, "state": "closed",
            "merged_at": "2026-11-23T18:59:17Z", "merge_commit_sha": SHA,
            "head": {"sha": HEAD},
            "base": {"ref": "main", "repo": {"full_name": REPO}},
        }],
    }
    options = (
        (SETUP_RUN, "Block 1 credential-free clean setup evidence",
         ".github/workflows/block1-clean-setup.yml", "nonroot-setup",
         "Reproduce README without root, inherited credentials or install",
         "block1-clean-setup-receipt", raw_setup, 1001),
        (ROLLBACK_RUN, "Block 1 isolated rollback rehearsal",
         ".github/workflows/block1-offline-revert-evidence.yml", "isolated-git-revert",
         "Reproduce offline Git revert and enforce production human gate",
         "block1-offline-revert-receipt", raw_rollback, 1002),
    )
    rows, blobs = [], {}
    for runid, name, workflow, job, step, artifact, raw, aid in options:
        rows.append({
            "id": runid, "name": name, "path": workflow,
            "event": "pull_request", "head_sha": HEAD, "run_attempt": 1,
            "status": "completed", "conclusion": "success",
        })
        output[prefix + "/actions/runs/" + str(runid) + "/jobs?per_page=100"] = {
            "total_count": 1,
            "jobs": [{
                "name": job, "run_id": runid, "head_sha": HEAD,
                "status": "completed", "conclusion": "success",
                "steps": [{"name": step, "status": "completed", "conclusion": "success"}],
            }],
        }
        url = "https://api.github.com" + prefix + "/actions/artifacts/" + str(aid) + "/zip"
        blobs[url] = raw
        output[prefix + "/actions/runs/" + str(runid) + "/artifacts?per_page=100"] = {
            "total_count": 1, "artifacts": [{
                "id": aid, "name": artifact, "expired": False,
                "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "size_in_bytes": len(raw), "archive_download_url": url,
                "workflow_run": {
                    "id": runid, "head_sha": HEAD,
                    "head_repository_id": 1387883686,
                },
            }],
        }
    output[prefix + "/actions/runs?head_sha=" + HEAD +
           "&event=pull_request&per_page=100"] = {
        "total_count": len(rows), "workflow_runs": rows,
    }
    runbooks = {
        "docs/RELEASE_AUTONOMY.md": "CI novo SHA humano nunca faz auto-merge health",
        "docs/BLOCK1_ISOLATED_ROLLBACK_EVIDENCE_20261106.md":
            "não produtivo production_rollback_executed=false schema_rollback_executed=false",
    }
    for path, value in runbooks.items():
        output[prefix + "/contents/" + path + "?ref=" + SHA] = {
            "content": base64.b64encode(value.encode()).decode(),
        }
    return output, blobs


def check(kind, *, mutate=None, env_overrides=None):
    data, blobs = fixture()
    if mutate:
        mutate(data, blobs)
    flags = env()
    flags.update(env_overrides or {})
    fn = verify_current_clean_setup if kind == "setup" else verify_current_isolated_rollback
    return fn(
        repository=REPO, assessed_commit=SHA, github_get=lambda path: data[path],
        archive_fetch=lambda url, token: blobs[url],
        environment=flags,
    )


class CurrentDocumentationEvidenceTests(unittest.TestCase):
    def test_both_current_merged_pr_proofs_are_source_verified(self):
        for kind, criterion in (("setup", "setup_configuration"),
                                ("rollback", "release_rollback")):
            with self.subTest(kind=kind):
                proof = check(kind)
                self.assertEqual(proof.criterion, criterion)
                self.assertEqual(proof.assessed_commit, SHA)
                self.assertEqual(proof.verification_state, "reviewed")
                self.assertEqual(len(proof.evidence), 2)
                self.assertIn(SHA, proof.evidence[0])
                self.assertIn("sha256:", proof.source)

    def test_expired_or_tampered_artifacts_are_never_passed(self):
        prefix = "/repos/" + REPO
        for kind, runid, item in (("setup", SETUP_RUN, 1001),
                                  ("rollback", ROLLBACK_RUN, 1002)):
            location = prefix + "/actions/runs/" + str(runid) + "/artifacts?per_page=100"
            with self.subTest(kind=kind, flaw="expired"):
                with self.assertRaises(CurrentDocumentationBlocked):
                    check(kind, mutate=lambda data, _: data[location]["artifacts"][0].update(expired=True))
            with self.subTest(kind=kind, flaw="digest"):
                with self.assertRaises(CurrentDocumentationBlocked):
                    check(kind, mutate=lambda data, _: data[location]["artifacts"][0].update(digest="sha256:" + "0" * 64))
            with self.subTest(kind=kind, flaw="wrong-source"):
                with self.assertRaises(CurrentDocumentationBlocked):
                    check(kind, mutate=lambda data, _: data[location]["artifacts"][0]["workflow_run"].update(head_sha="e" * 40))

    def test_wrong_merge_identity_tree_or_runner_fail_closed(self):
        prefix = "/repos/" + REPO
        problems = (
            lambda data, _: data[prefix + "/commits/" + SHA]["commit"]["tree"].update(sha="d" * 40),
            lambda data, _: data[prefix + "/commits/" + HEAD + "/pulls?per_page=100"][0].update(merged_at=None),
            lambda data, _: data[prefix + "/actions/runs/" + str(CURRENT)].update(run_attempt=2),
        )
        for mutate in problems:
            with self.subTest(problem=str(mutate)), self.assertRaises(CurrentDocumentationBlocked):
                check("setup", mutate=mutate)
        with self.assertRaises(CurrentDocumentationBlocked):
            check("rollback", env_overrides={"GITHUB_REF": "refs/heads/untrusted"})

    def test_no_source_job_execution_does_not_pass(self):
        prefix = "/repos/" + REPO
        path = prefix + "/actions/runs/" + str(SETUP_RUN) + "/jobs?per_page=100"
        with self.assertRaises(CurrentDocumentationBlocked):
            check("setup", mutate=lambda data, _: data[path]["jobs"][0].update(conclusion="failure"))

    def test_forged_zip_bytes_rejected_even_if_metadata_success(self):
        def modify(data, blobs):
            key = next(k for k in blobs if "/1001/" in k)
            blobs[key] = b"not a GitHub Actions artifact"
        with self.assertRaises(CurrentDocumentationBlocked):
            check("setup", mutate=modify)


if __name__ == "__main__":
    unittest.main()
