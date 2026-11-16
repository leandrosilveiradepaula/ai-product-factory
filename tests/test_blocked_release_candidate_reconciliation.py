"""Offline negative tests for real blocked-release candidate recovery."""
import copy
import unittest
from types import SimpleNamespace

from ai_product_factory.blocked_release_candidate_reconciliation import (
    reconcile_one, verify_blocked_release_candidate,
)

REPO = "example/product"
PID = "11111111-1111-1111-1111-111111111111"
CS = "22222222-2222-2222-2222-222222222222"
RUN = "33333333-3333-3333-3333-333333333333"
TASK = "44444444-4444-4444-4444-444444444444"
BRANCH = "factory/change-set-22222222"
ORIGINAL = "a" * 40
PRIOR = "b" * 40
NEW = "c" * 40


class FakeGithub:
    repository = REPO
    def __init__(self):
        self.pr_sha = NEW
        self.pr_state = "open"
        self.pr_merged = False
        self.pr_draft = False
        self.branch_sha = NEW
        self.check_status = "success"
        self.check_head = NEW
        self.compare_behind_by = 0
        self.run_status = "success"
        self.calls = []

    def get_pull_request(self, number):
        self.calls.append(("pr", number))
        return SimpleNamespace(
            number=number, head_sha=self.pr_sha, state=self.pr_state,
            merged=self.pr_merged, draft=self.pr_draft, head_repository=REPO,
            head_ref=BRANCH, base_ref="main",
        )

    def get_branch_sha(self, branch):
        self.calls.append(("branch", branch))
        return self.branch_sha

    def compare_commits(self, old, new):
        self.calls.append(("compare", old, new))
        return {"status": "ahead", "behind_by": self.compare_behind_by,
                "ahead_by": 7 if old == ORIGINAL else 5}

    def _call(self, method, path, *, query):
        self.calls.append((method, path))
        if path.endswith("/check-runs"):
            return {"total_count": 2, "check_runs": [
                {"name": name, "status": "completed", "conclusion": self.check_status,
                 "head_sha": self.check_head, "app": {"slug": "github-actions"}}
                for name in ("candidate", "tenant-rls-postgres")
            ]}
        if path.endswith("/actions/runs"):
            return {"total_count": 1, "workflow_runs": [{
                "id": 123456, "head_sha": NEW, "head_branch": BRANCH,
                "path": ".github/workflows/validate.yml",
                "status": "completed", "conclusion": self.run_status,
                "repository": {"full_name": REPO},
            }]}
        raise AssertionError(path)


class Fixture:
    def __init__(self):
        self.project = {
            "id": PID, "project_kind": "greenfield",
            "repository": REPO, "is_active": True,
        }
        self.cs = {
            "id": CS, "project_id": PID, "release_run_id": RUN, "root_task_id": TASK,
            "status": "ci_pending", "candidate_commit": PRIOR,
            "integration_branch": BRANCH, "lease_owner": None,
            "lease_expires_at": None, "metadata": {
                "integration_release_request": {
                    "branch": BRANCH, "candidate_commit": PRIOR,
                    "pr_number": 2, "issue_number": 1,
                },
                "integration_epoch_receipt": {
                    "candidate_commit": PRIOR, "generation": 1,
                    "project_id": PID, "wave": 9,
                },
            },
        }
        self.run = {
            "id": RUN, "task_id": TASK,
            "candidate_commit": PRIOR, "branch_name": BRANCH,
            "status": "release_policy_blocked",
            "lease_owner": None, "lease_expires_at": None,
            "metadata": {
                "source": "change-set", "change_set_id": CS,
                "execution_generation": 1,
                "specialist_lanes": {"candidate_commit": PRIOR},
            },
        }
        self.report = {
            "status": "blocked", "candidate_commit": PRIOR,
            "report": {"release_state": "blocked"},
        }
        self.control = {"project_id": PID, "state": "running", "generation": 1}
        self.create = {"head_sha": ORIGINAL, "pr": 2, "change_set_id": CS}
        self.prior = {
            "change_set_id": CS, "previous_commit": ORIGINAL,
            "old_sha": ORIGINAL, "new_sha": PRIOR,
            "candidate_commit": PRIOR, "compare_status": "ahead",
        }
        self.gh = FakeGithub()

    def verify(self):
        return verify_blocked_release_candidate(
            self.gh, project=self.project, change_set=self.cs,
            run=self.run, report=self.report, control=self.control,
            create_receipt=self.create, last_reconciliation=self.prior,
        )


class FakeStore:
    def __init__(self, fixture):
        self.fixture = fixture
        self.calls = []
        self.writes = []
    def get(self, table, query):
        self.calls.append((table, query))
        data = {
            "factory_change_sets": [{"metadata": copy.deepcopy(self.fixture.cs)}],
            "factory_runs": [self.fixture.run],
            "factory_projects": [self.fixture.project],
            "factory_project_execution_controls": [self.fixture.control],
            "factory_release_reports": [self.fixture.report],
            "factory_tool_usage": [],
        }
        if table == "factory_change_sets":
            return [copy.deepcopy(self.fixture.cs)]
        if table == "factory_tool_usage":
            if "operation=eq.create_pr" in query:
                return [{"metadata": self.fixture.create}]
            if "operation=eq.reconcile_pr_candidate" in query:
                return [{"metadata": self.fixture.prior}]
            raise AssertionError(query)
        return copy.deepcopy(data[table])
    def rpc(self, name, payload):
        self.writes.append((name, payload))
        return {
            "status": "ci_pending", "run_id": RUN, "change_set_id": CS,
            "candidate_commit": NEW, "previous_commit": PRIOR,
            "fresh_ci_required": True, "fresh_specialists_required": True,
            "fresh_preview_required": True, "release_authorized": False,
        }


class BlockedReleaseCandidateTests(unittest.TestCase):
    def test_real_lineage_preserves_original_and_new_ci_proof(self):
        f = Fixture()
        evidence = f.verify()
        self.assertEqual(evidence["old_sha"], ORIGINAL)
        self.assertEqual(evidence["new_sha"], NEW)
        self.assertEqual(evidence["prior_candidate_commit"], PRIOR)
        self.assertEqual(evidence["ahead_by"], 7)
        self.assertEqual(evidence["prior_ahead_by"], 5)
        self.assertEqual(evidence["ci_run_id"], 123456)
        self.assertEqual(len(evidence["ci_checks"]), 2)
        self.assertFalse(evidence["release_authorized"])
        self.assertFalse(evidence["historical_approvals_replayed"])
        self.assertEqual(sum(x[0] == "pr" for x in f.gh.calls), 2)

    def test_dry_run_never_writes(self):
        f = Fixture()
        store = FakeStore(f)
        receipt = reconcile_one(CS, RUN, store=store,
                                github_factory=lambda repository: f.gh)
        self.assertEqual(receipt["status"], "preflight_verified")
        self.assertEqual(receipt["candidate_commit"], NEW)
        self.assertEqual(receipt["writes"], 0)
        self.assertEqual(store.writes, [])
        self.assertNotIn("service_role", str(receipt).lower())

    def test_apply_requires_verified_rpc_receipt(self):
        f = Fixture()
        store = FakeStore(f)
        result = reconcile_one(CS, RUN, apply=True, store=store,
                               github_factory=lambda repository: f.gh)
        self.assertEqual(result["status"], "ci_pending")
        self.assertEqual(result["candidate_commit"], NEW)
        self.assertEqual(len(store.writes), 1)
        name, payload = store.writes[0]
        self.assertEqual(name, "factory_reconcile_blocked_release_candidate_once_v1")
        self.assertEqual(payload["p_github_evidence"]["original_head_sha"], ORIGINAL)
        self.assertEqual(payload["p_prior_candidate"], PRIOR)

    def test_unverified_rpc_receipt_rejected(self):
        f = Fixture()
        store = FakeStore(f)
        def incorrect(name, payload):
            return {"status": "ready_for_human_release", "release_authorized": True}
        store.rpc = incorrect
        with self.assertRaises(PermissionError):
            reconcile_one(CS, RUN, apply=True, store=store,
                          github_factory=lambda repository: f.gh)

    def test_pr_merged_or_changed_disallowed(self):
        for attribute, value in (
            ("pr_sha", PRIOR), ("pr_state", "closed"),
            ("pr_merged", True), ("pr_draft", True),
            ("branch_sha", PRIOR),
        ):
            with self.subTest(attribute=attribute):
                f = Fixture()
                setattr(f.gh, attribute, value)
                with self.assertRaises(PermissionError):
                    f.verify()

    def test_old_boundaries_and_stale_generation_fail(self):
        for obj, key, value in (
            ("run", "status", "awaiting_release"),
            ("run", "lease_owner", "worker"),
            ("run", "candidate_commit", NEW),
            ("cs", "candidate_commit", NEW),
            ("cs", "status", "completed"),
            ("cs", "lease_owner", "worker"),
            ("control", "state", "stopped"),
            ("control", "generation", 2),
            ("report", "status", "released"),
            ("report", "candidate_commit", NEW),
        ):
            with self.subTest(obj=obj, key=key):
                f = Fixture()
                getattr(f, obj)[key] = value
                with self.assertRaises(PermissionError):
                    f.verify()

    def test_previous_receipts_can_never_be_reinterpreted(self):
        for key, value in (
            ("head_sha", PRIOR),
            ("change_set_id", PID),
        ):
            f = Fixture()
            f.create[key] = value
            with self.assertRaises(PermissionError):
                f.verify()
        for key, value in (
            ("old_sha", PRIOR), ("candidate_commit", NEW),
            ("previous_commit", PRIOR), ("new_sha", NEW),
        ):
            f = Fixture()
            f.prior[key] = value
            with self.assertRaises(PermissionError):
                f.verify()

    def test_missing_history_unexplained_candidate_drift(self):
        f = Fixture()
        f.prior = None
        with self.assertRaises(PermissionError):
            f.verify()
        f.run["candidate_commit"] = ORIGINAL
        f.cs["candidate_commit"] = ORIGINAL
        f.cs["metadata"]["integration_release_request"]["candidate_commit"] = ORIGINAL
        f.cs["metadata"]["integration_epoch_receipt"]["candidate_commit"] = ORIGINAL
        f.report["candidate_commit"] = ORIGINAL
        f.prior = None
        evidence = f.verify()
        self.assertEqual(evidence["old_sha"], ORIGINAL)

    def test_native_ci_and_nonfastforward_denied(self):
        for attr, value in (
            ("check_status", "failure"), ("check_head", PRIOR),
            ("run_status", "failure"), ("compare_behind_by", 1),
        ):
            with self.subTest(attr=attr):
                f = Fixture()
                setattr(f.gh, attr, value)
                with self.assertRaises(PermissionError):
                    f.verify()

    def test_missing_current_pr_or_inconsistent_epoch_denied(self):
        f = Fixture()
        f.cs["metadata"]["integration_epoch_receipt"]["generation"] = 0
        with self.assertRaises(PermissionError):
            f.verify()
        f = Fixture()
        f.run["metadata"]["source"] = "operator_reconciled_dogfood"
        with self.assertRaises(PermissionError):
            f.verify()

    def test_pr_head_move_during_ci_is_rejected(self):
        f = Fixture()
        original = f.gh.get_pull_request
        calls = {"count": 0}
        def moved(number):
            calls["count"] += 1
            if calls["count"] == 2:
                f.gh.pr_sha = PRIOR
            return original(number)
        f.gh.get_pull_request = moved
        with self.assertRaises(PermissionError):
            f.verify()
        self.assertEqual(calls["count"], 2)

    def test_non_native_status_cannot_replace_github_actions_ci(self):
        f = Fixture()
        original = f.gh._call
        def only_external(method, path, *, query):
            data = original(method, path, query=query)
            if path.endswith("/check-runs"):
                for check in data["check_runs"]:
                    check["app"]["slug"] = "external-provider"
            return data
        f.gh._call = only_external
        with self.assertRaises(PermissionError):
            f.verify()

    def test_native_workflow_must_be_at_exact_integrated_branch(self):
        f = Fixture()
        original = f.gh._call
        def stale_branch(method, path, *, query):
            data = original(method, path, query=query)
            if path.endswith("/actions/runs"):
                data["workflow_runs"][0]["head_branch"] = "factory/other"
            return data
        f.gh._call = stale_branch
        with self.assertRaises(PermissionError):
            f.verify()

    def test_invalid_ids_never_reach_read_or_write(self):
        f = Fixture()
        store = FakeStore(f)
        for cs, run in (("not-a-uuid", RUN), (CS, "wrong"), ("", "")):
            with self.assertRaises(PermissionError):
                reconcile_one(cs, run, apply=True, store=store,
                              github_factory=lambda repository: f.gh)
        self.assertEqual(store.calls, [])
        self.assertEqual(store.writes, [])


if __name__ == "__main__":
    unittest.main()
