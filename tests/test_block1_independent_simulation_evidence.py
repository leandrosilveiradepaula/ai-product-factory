"""Fail-closed independent tests for B2 executed simulation evidence."""
import copy
import unittest

from ai_product_factory.independent_simulation_runtime_evidence import (
    REPO, REQUIRED_MODULES, REQUIRED_EXECUTED_TEST, TRUSTED_EXECUTED_TEST_BLOB,
    RuntimeSimulationEvidenceBlocked, verify_executed_simulation_inventory,
)

SHA = "a" * 40
RUN = 1001
INVENTORY = {
    "scope": "source_markers_not_runtime_reachability",
    "source_files": 30, "marker_occurrences_by_line": 12,
    "fingerprint": "b" * 64,
    "locations": [{"path": "src/ai_product_factory/worker.py",
                   "line": i + 1, "kinds": ["simulation"]} for i in range(12)],
    "paid_calls": 0, "writes_to_production": 0, "independent_pass": False,
}
REACHABLE = {
    "scope": "static-runtime-cli-import-closure-and-guard-classification-not_runtime_proof",
    "entrypoint": "src/ai_product_factory/runtime_cli.py",
    "reachable_modules": ["runtime_cli", "runtime_auth"],
    "unclassified_runtime_markers": [],
    "simulation_can_authorize_release": False,
    "independent_pass": False,
    "paid_calls": 0, "writes": 0,
}
REACHABLE["scope"] = (
    "static-runtime-cli-import-closure-and-guard-classification-not-runtime-proof"
)


def github(expected_sha=SHA, override=None):
    tree = [{"path": p, "sha": TRUSTED_EXECUTED_TEST_BLOB if p == REQUIRED_EXECUTED_TEST
             else "c" * 40, "type": "blob"} for p in sorted(REQUIRED_MODULES)]
    values = {
        f"/repos/{REPO}/git/trees/{expected_sha}?recursive=1":
            {"truncated": False, "tree": tree},
        f"/repos/{REPO}/actions/runs?head_sha={expected_sha}&per_page=100":
            {"total_count": 1, "workflow_runs": [
                {"id": RUN, "name": "validate", "event": "push", "head_branch": "main",
                 "head_sha": expected_sha, "status": "completed", "conclusion": "success"}]},
        f"/repos/{REPO}/actions/runs/{RUN}/jobs?per_page=100":
            {"jobs": [{"name": name, "status": "completed", "conclusion": "success"}
                      for name in ("test", "factory-acceptance")]},
    }
    if override is not None:
        override(values)
    def get(path):
        # An unavailable source must be treated as an invalid receipt by the
        # verifier, never as a success or an unrelated test harness error.
        return values.get(path)
    return get


def verify(*, get=None, inventory=None, reachability=None, sha=SHA):
    return verify_executed_simulation_inventory(
        repository=REPO, assessed_commit=sha,
        github_get=get or github(), source_inventory=copy.deepcopy(inventory or INVENTORY),
        runtime_reachability=copy.deepcopy(reachability or REACHABLE),
    )


class B2IndependentSimulationEvidenceTests(unittest.TestCase):
    def test_reverified_exact_sha_test_and_two_green_jobs_gives_bounded_proof(self):
        proof = verify()
        self.assertEqual(proof.domain, "functional_completeness")
        self.assertEqual(proof.criterion, "mock_noop_demo_inventory")
        self.assertEqual(proof.assessed_commit, SHA)
        self.assertIn(SHA, proof.evidence[0])
        receipt = proof.retained_receipt
        self.assertEqual(receipt["unclassified_runtime_markers"], 0)
        self.assertFalse(receipt["live_authn_authz_certified"])
        self.assertFalse(receipt["critical_e2e_certified"])
        self.assertFalse(receipt["production_release_observed"])
        self.assertEqual(receipt["production_writes"], 0)
        self.assertEqual(receipt["paid_calls"], 0)

    def test_changed_executable_test_source_denied(self):
        def altered(values):
            values[f"/repos/{REPO}/git/trees/{SHA}?recursive=1"]["tree"][0]["sha"] = "d" * 40
            for row in values[f"/repos/{REPO}/git/trees/{SHA}?recursive=1"]["tree"]:
                if row["path"] == REQUIRED_EXECUTED_TEST:
                    row["sha"] = "d" * 40
        with self.assertRaisesRegex(RuntimeSimulationEvidenceBlocked, "test_source_changed"):
            verify(get=github(override=altered))

    def test_failed_or_missing_required_ci_job_denied(self):
        for outcome in ("failure", "cancelled", "skipped"):
            def alter(values):
                values[f"/repos/{REPO}/actions/runs/{RUN}/jobs?per_page=100"]["jobs"][0]["conclusion"] = outcome
            with self.subTest(outcome=outcome), self.assertRaises(RuntimeSimulationEvidenceBlocked):
                verify(get=github(override=alter))
        def absent(values):
            values[f"/repos/{REPO}/actions/runs/{RUN}/jobs?per_page=100"]["jobs"].pop()
        with self.assertRaises(RuntimeSimulationEvidenceBlocked):
            verify(get=github(override=absent))

    def test_wrong_sha_or_pr_ci_does_not_count(self):
        with self.assertRaises(RuntimeSimulationEvidenceBlocked):
            verify(sha="b" * 40)
        def altered(values):
            values[f"/repos/{REPO}/actions/runs?head_sha={SHA}&per_page=100"]["workflow_runs"][0]["event"] = "pull_request"
        with self.assertRaises(RuntimeSimulationEvidenceBlocked):
            verify(get=github(override=altered))

    def test_static_unclassified_marker_or_inconsistent_inventory_denied(self):
        reach = dict(REACHABLE, unclassified_runtime_markers=[{"constant": "DEMO"}])
        with self.assertRaises(RuntimeSimulationEvidenceBlocked):
            verify(reachability=reach)
        inv = dict(INVENTORY, marker_occurrences_by_line=13)
        with self.assertRaises(RuntimeSimulationEvidenceBlocked):
            verify(inventory=inv)
        inv = dict(INVENTORY, writes_to_production=1)
        with self.assertRaises(RuntimeSimulationEvidenceBlocked):
            verify(inventory=inv)

    def test_missing_or_truncated_tree_never_certifies(self):
        for mode in ("truncate", "remove"):
            def alter(values):
                value = values[f"/repos/{REPO}/git/trees/{SHA}?recursive=1"]
                if mode == "truncate":
                    value["truncated"] = True
                else:
                    value["tree"] = value["tree"][1:]
            with self.subTest(mode=mode), self.assertRaises(RuntimeSimulationEvidenceBlocked):
                verify(get=github(override=alter))


if __name__ == "__main__":
    unittest.main()
