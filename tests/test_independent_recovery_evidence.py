import unittest

from ai_product_factory.independent_recovery_evidence import (
    REPOSITORY, REQUIRED_JOBS, SOURCE_FILES, SOURCE_RUN, SOURCE_SHA,
    RecoveryEvidenceBlocked, verify_recovery_alerting,
)

SHA = "b" * 40
ROOT = "/repos/" + REPOSITORY


def environment():
    return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_EVENT_NAME": "workflow_run", "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_REF": REPOSITORY + "/.github/workflows/autonomous-runner.yml@refs/heads/main",
            "GITHUB_RUN_ID": "9"}


def event():
    return {"workflow_run": {"id": 8, "name": "validate", "path": ".github/workflows/validate.yml",
            "event": "push", "status": "completed", "conclusion": "success", "head_sha": SHA,
            "head_branch": "main", "run_attempt": 1, "repository": {"full_name": REPOSITORY}}}


def tree(seed):
    return {"truncated": False, "tree": [
        {"path": path, "type": "blob", "mode": "100644", "sha": seed * 40}
        for path in sorted(SOURCE_FILES)
    ]}


def fixture():
    jobs = [{"name": name, "run_id": SOURCE_RUN, "head_sha": SOURCE_SHA,
             "status": "completed", "conclusion": "success"} for name in REQUIRED_JOBS]
    return {
        ROOT + "/actions/runs/9": {"id": 9, "name": "Factory autonomous runner", "path": ".github/workflows/autonomous-runner.yml", "event": "workflow_run", "head_sha": SHA, "head_branch": "main", "run_attempt": 1, "status": "in_progress"},
        ROOT + "/actions/runs/" + str(SOURCE_RUN): {"id": SOURCE_RUN, "name": "Factory autonomous runner", "path": ".github/workflows/autonomous-runner.yml", "event": "schedule", "head_sha": SOURCE_SHA, "head_branch": "main", "run_attempt": 1, "status": "completed", "conclusion": "success", "repository": {"full_name": REPOSITORY}},
        ROOT + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100": {"jobs": jobs},
        ROOT + "/compare/" + SOURCE_SHA + "..." + SHA: {"status": "ahead", "behind_by": 0, "merge_base_commit": {"sha": SOURCE_SHA}},
        ROOT + "/git/trees/" + SOURCE_SHA + "?recursive=1": tree("a"),
        ROOT + "/git/trees/" + SHA + "?recursive=1": tree("a"),
        ROOT + "/git/ref/heads/main": {"object": {"sha": SHA}},
    }


class RecoveryEvidenceTests(unittest.TestCase):
    def prove(self, rows):
        return verify_recovery_alerting(repository=REPOSITORY, assessed_commit=SHA,
            github_get=lambda path: rows[path], environment=environment(), event_payload=event())

    def test_source_bound_scheduler_recovery_passes(self):
        proof = self.prove(fixture())
        self.assertEqual(proof.criterion, "recovery_alerting")
        self.assertEqual(proof.retained_receipt["source_run_id"], SOURCE_RUN)

    def test_job_sha_ancestry_or_operational_blob_drift_blocks(self):
        for mutation in ("job", "sha", "ancestor", "blob"):
            rows = fixture()
            if mutation == "job":
                rows[ROOT + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
            elif mutation == "sha":
                rows[ROOT + "/actions/runs/" + str(SOURCE_RUN)]["head_sha"] = SHA
            elif mutation == "ancestor":
                rows[ROOT + "/compare/" + SOURCE_SHA + "..." + SHA]["behind_by"] = 1
            else:
                rows[ROOT + "/git/trees/" + SHA + "?recursive=1"]["tree"][0]["sha"] = "c" * 40
            with self.subTest(mutation=mutation), self.assertRaises(RecoveryEvidenceBlocked):
                self.prove(rows)
