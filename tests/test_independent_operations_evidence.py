import unittest

from ai_product_factory.independent_operations_evidence import (
    REPOSITORY, REQUIRED_JOBS, SOURCE_FILES, SOURCE_RUN, SOURCE_SHA,
    OperationsEvidenceBlocked, verify_operations_runbook,
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
    return {"truncated": False, "tree": [{"path": path, "type": "blob", "mode": "100644", "sha": seed * 40}
                                           for path in sorted(SOURCE_FILES)]}


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


class OperationsEvidenceTests(unittest.TestCase):
    def prove(self, rows):
        return verify_operations_runbook(repository=REPOSITORY, assessed_commit=SHA,
            github_get=lambda path: rows[path], environment=environment(), event_payload=event())

    def test_source_bound_runbook_and_operations_run_passes(self):
        proof = self.prove(fixture())
        self.assertEqual((proof.domain, proof.criterion), ("documentation", "operations"))
        self.assertEqual(proof.retained_receipt["source_run_id"], SOURCE_RUN)
        self.assertEqual(proof.retained_receipt["scope"],
                         "exact_operational_runbooks_and_executable_commands_only")
        self.assertFalse(proof.retained_receipt["governance_contract_proved_by_this_criterion"])

    def test_governance_preface_does_not_invalidate_executed_operations(self):
        # A planning document is not an executable operations runbook. It is
        # covered by the independent requirements inventory instead.
        self.assertNotIn("docs/FINALIZATION_EXECUTION_CONTRACT.md", SOURCE_FILES)
        rows = fixture()
        for digest, suffix in (("a" * 40, "source"), ("f" * 40, "assessed")):
            path = (ROOT + "/git/trees/" + SOURCE_SHA + "?recursive=1"
                    if suffix == "source" else
                    ROOT + "/git/trees/" + SHA + "?recursive=1")
            rows[path]["tree"].append({
                "path": "docs/FINALIZATION_EXECUTION_CONTRACT.md",
                "type": "blob", "mode": "100644", "sha": digest,
            })
        self.assertEqual(self.prove(rows).criterion, "operations")

    def test_job_event_ancestry_and_each_bound_file_drift_block(self):
        for mutation in ("job", "event", "ancestor", "blob", "missing"):
            rows = fixture()
            if mutation == "job":
                rows[ROOT + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
            elif mutation == "event":
                rows[ROOT + "/actions/runs/" + str(SOURCE_RUN)]["event"] = "workflow_dispatch"
            elif mutation == "ancestor":
                rows[ROOT + "/compare/" + SOURCE_SHA + "..." + SHA]["behind_by"] = 1
            elif mutation == "blob":
                rows[ROOT + "/git/trees/" + SHA + "?recursive=1"]["tree"][0]["sha"] = "c" * 40
            else:
                rows[ROOT + "/git/trees/" + SHA + "?recursive=1"]["tree"].pop()
            with self.subTest(mutation=mutation), self.assertRaises(OperationsEvidenceBlocked):
                self.prove(rows)
