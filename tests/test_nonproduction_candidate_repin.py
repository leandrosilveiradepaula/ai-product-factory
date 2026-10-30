import unittest
from io import BytesIO
from urllib.error import HTTPError
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from ai_product_factory.nonproduction_candidate_repin import (
    ExistingCandidatePolicy, NativeCIWorkflowPolicy, repin_existing_projects,
    repin_project, verify_candidate, _post_rpc,
)
from ai_product_factory.pinned_nonproduction_target import PinnedNonproductionTarget
from ai_product_factory.supabase_server import SupabaseServerConfig


OLD = "a" * 40
NEW = "b" * 40


def project(key="crm-infodive", repo="leandrosilveiradepaula/crm-infodive", *, sha=OLD):
    return {
        "id": key + "-id", "project_key": key, "repository": repo,
        "project_kind": "existing", "is_active": True,
        "manifest": {"delivery_target": {
            "schema_version": 1, "mode": "open_pr_candidate", "repository": repo,
            "branch": "preview/candidate", "sha": sha, "candidate_pr_number": 56,
            "repin_policy": {"schema_version": 1, "enabled": True, "native_ci": {
                "schema_version": 1, "workflow_path": ".github/workflows/validation.yml",
                "workflow_name": "Repository validation", "workflow_id": 12, "event": "pull_request",
            }},
        }},
        "execution_control": {"state": "running", "generation": 6, "version": 9},
    }


def github(repo, *, conclusion="success", attempt=2):
    g = MagicMock()
    g.repository = repo
    g.get_branch_sha.return_value = NEW
    g.get_pull_request.return_value = SimpleNamespace(
        number=56, state="open", merged=False, head_sha=NEW, head_ref="preview/candidate",
        head_repository=repo, base_ref="main", draft=False)
    g.compare_commits.return_value = {"status": "ahead", "ahead_by": 4, "behind_by": 0}
    g._call.return_value = {"total_count": 1, "workflow_runs": [{
        "id": 99, "workflow_id": 12, "run_number": 44, "run_attempt": attempt,
        "name": "Repository validation", "path": ".github/workflows/validation.yml",
        "event": "pull_request", "head_sha": NEW, "head_branch": "preview/candidate",
        "status": "completed", "conclusion": conclusion,
    }]}
    return g


def receipt(body):
    return {"status": "updated", "project_key": body["p_project_key"],
            "old_sha": body["p_expected_sha"], "new_sha": body["p_new_sha"],
            "generation": body["p_expected_generation"] + 1,
            "version": body["p_expected_version"] + 1}


def project_fetcher(projects):
    """PostgREST mock honoring exact offset and limit, including controller GETs."""
    ordered = sorted(projects, key=lambda p: p["project_key"])
    def get(url, headers):
        _ = headers
        q = parse_qs(urlsplit(url).query)
        if "factory_project_execution_controls" in url:
            pid = q["project_id"][0].removeprefix("eq.")
            return [p["execution_control"] for p in ordered if p["id"] == pid]
        if "factory_projects" in url:
            rows = ordered
            if "project_key" in q:
                requested = q["project_key"][0].removeprefix("eq.")
                rows = [p for p in ordered if p["project_key"] == requested]
            offset = int(q.get("offset", ["0"])[0])
            limit = int(q.get("limit", ["20"])[0])
            return [{k: v for k, v in p.items() if k != "execution_control"}
                    for p in rows[offset:offset + limit]]
        raise AssertionError("unexpected read endpoint")
    return get


class CandidateRePinTests(unittest.TestCase):
    @staticmethod
    def mock_config():
        return patch("ai_product_factory.nonproduction_candidate_repin.resolve_supabase_server_config",
                     return_value=SupabaseServerConfig("https://example.test", "key", {"apikey": "key"}))

    def policy(self):
        item = project()
        return ExistingCandidatePolicy.parse(item["manifest"], repository=item["repository"])

    def test_verified_exact_sha_uses_declared_repository_workflow(self):
        policy = self.policy()
        result = verify_candidate(github(policy.target.repository), target=policy.target, ci_policy=policy.ci, new_sha=NEW)
        self.assertEqual(result["ci_sha"], NEW)
        self.assertEqual(result["ci_workflow_path"], ".github/workflows/validation.yml")
        self.assertEqual(result["ci_run_attempt"], 2)
        self.assertEqual(result["source"], "github_actions_exact_sha")

    def test_latest_retry_governs_not_an_older_success(self):
        policy = self.policy(); g = github(policy.target.repository)
        older = g._call.return_value["workflow_runs"][0]
        newest = {**older, "id": 100, "run_attempt": 3, "conclusion": "failure"}
        g._call.return_value = {"total_count": 2, "workflow_runs": [older, newest]}
        with self.assertRaisesRegex(PermissionError, "latest"):
            verify_candidate(g, target=policy.target, ci_policy=policy.ci, new_sha=NEW)

    def test_rejects_vercel_cross_workflow_and_incomplete_evidence(self):
        policy = self.policy()
        for mutate in (
            {"name": "Vercel Preview Comments"}, {"path": ".github/workflows/vercel.yml"},
            {"event": "issue_comment"}, {"head_sha": OLD}, {"head_branch": "other"},
            {"status": "in_progress", "conclusion": None}, {"workflow_id": None}, {"workflow_id": 77},
        ):
            g = github(policy.target.repository)
            g._call.return_value["workflow_runs"][0].update(mutate)
            with self.subTest(mutate=mutate), self.assertRaises(PermissionError):
                verify_candidate(g, target=policy.target, ci_policy=policy.ci, new_sha=NEW)

    def test_policy_is_explicit_and_fails_closed_without_it(self):
        item = project(); del item["manifest"]["delivery_target"]["repin_policy"]
        with self.assertRaisesRegex(PermissionError, "explicitly enabled"):
            ExistingCandidatePolicy.parse(item["manifest"], repository=item["repository"])
        for invalid in ({}, {"schema_version": 1, "workflow_path": "ci.yml", "workflow_name": "x", "workflow_id": 1, "event": "pull_request"}):
            with self.subTest(invalid=invalid), self.assertRaises(PermissionError):
                NativeCIWorkflowPolicy.parse(invalid)

    def test_repin_rpc_receives_current_epoch_and_exact_evidence(self):
        item = project(); g = github(item["repository"]); rpc = MagicMock(side_effect=lambda _name, body: receipt(body))
        result = repin_project(item, github_factory=lambda _: g, rpc=rpc)
        self.assertEqual(result["status"], "updated")
        body = rpc.call_args.args[1]
        self.assertEqual(body["p_expected_generation"], 6)
        self.assertEqual(body["p_expected_version"], 9)
        self.assertEqual(body["p_evidence"]["ci_sha"], NEW)
        self.assertNotIn("merge", str(body).lower())

    def test_postgrest_409_remains_blocked_and_never_leaks_sql_details(self):
        upstream = HTTPError(
            "https://example.test/rest/v1/rpc/factory_repin_nonproduction_target_v1",
            409,"private_sql_detail",{},BytesIO(b'{"message":"secret internal"}'))
        with self.mock_config(), patch(
            "ai_product_factory.nonproduction_candidate_repin.request.urlopen",
            side_effect=upstream,
        ):
            with self.assertRaises(PermissionError) as caught:
                _post_rpc("factory_repin_nonproduction_target_v1", {"p_project_key":"crm-infodive"})
        self.assertEqual(str(caught.exception),"candidate repin CAS conflict (HTTP 409)")
        self.assertNotIn("secret internal",str(caught.exception))

    def test_candidate_cas_conflict_is_bounded_blocked_not_transport_error(self):
        p=project()
        fetch=project_fetcher([p])
        with self.mock_config():
            result=repin_existing_projects(
                max_projects=1,rotation_slot=0,
                project_fetcher=fetch,control_fetcher=fetch,
                github_factory=lambda repo:github(repo),
                rpc=lambda name,body: (_ for _ in ()).throw(
                    PermissionError("candidate repin CAS conflict (HTTP 409)")))
        self.assertEqual(result["status"],"partial_failure")
        self.assertEqual(result["results"][0]["status"],"blocked")
        self.assertEqual(result["results"][0]["reason_code"],"candidate_cas_conflict")

    def test_unchanged_candidate_does_not_need_ci_or_call_rpc(self):
        item = project(); g = github(item["repository"]); g.get_branch_sha.return_value = OLD; rpc = MagicMock()
        result = repin_project(item, github_factory=lambda _: g, rpc=rpc)
        self.assertEqual(result["status"], "unchanged")
        g._call.assert_not_called(); rpc.assert_not_called()

    def test_two_existing_projects_are_independent_after_first_error(self):
        first, second = project("alpha", "owner/alpha"), project("beta", "owner/beta")
        fetch = project_fetcher([first, second])
        def factory(repo):
            if repo == "owner/alpha":
                raise RuntimeError("cross-repo token unavailable")
            return github(repo)
        with self.mock_config():
            result = repin_existing_projects(max_projects=2, rotation_slot=0,
                                             project_fetcher=fetch, control_fetcher=fetch,
                                             github_factory=factory, rpc=lambda _name, body: receipt(body))
        self.assertEqual([row["status"] for row in result["results"]], ["error", "updated"])
        self.assertEqual(result["status"], "partial_failure")
        self.assertEqual(result["results"][1]["project_key"], "beta")


    def test_verified_draft_new_sha_is_deferred_without_any_write_or_ci(self):
        p = project()
        g = github(p["repository"])
        g.get_pull_request.return_value.draft = True
        rpc = MagicMock()
        result = repin_project(p, github_factory=lambda _: g, rpc=rpc)
        self.assertEqual(result, {
            "status": "deferred", "project_key": p["project_key"],
            "reason_code": "candidate_draft_hold", "observed_sha": NEW})
        rpc.assert_not_called()
        g._call.assert_not_called()
        self.assertGreaterEqual(g.get_pull_request.call_count, 2)

    def test_draft_hold_never_suppresses_real_drift_or_missing_evidence(self):
        for mode in ("wrong-pr", "wrong-repo", "not-descendant", "branch-drift",
                     "pr-moved", "missing-draft"):
            p = project()
            g = github(p["repository"])
            pr = g.get_pull_request.return_value
            pr.draft = True
            if mode == "wrong-pr":
                pr.number = 77
            if mode == "wrong-repo":
                pr.head_repository = "other/foreign"
            if mode == "not-descendant":
                g.compare_commits.return_value = {"status": "diverged", "ahead_by": 1, "behind_by": 1}
            if mode == "branch-drift":
                g.get_branch_sha.side_effect = [NEW, OLD]
            if mode == "pr-moved":
                valid = SimpleNamespace(**vars(pr))
                changed = SimpleNamespace(**{**vars(pr), "head_sha": OLD})
                g.get_pull_request.side_effect = [valid, changed]
            if mode == "missing-draft":
                pr.draft = None
            rpc = MagicMock()
            with self.subTest(mode=mode), self.assertRaises(PermissionError):
                repin_project(p, github_factory=lambda _: g, rpc=rpc)
            rpc.assert_not_called()

    def test_draft_hold_is_nonfailing_batch_but_failure_still_blocks(self):
        first = project("alpha", "owner/alpha")
        second = project("beta", "owner/beta")
        fetch = project_fetcher([first, second])
        def factory(repo):
            g = github(repo)
            if repo == "owner/alpha":
                g.get_pull_request.return_value.draft = True
            else:
                g.get_pull_request.return_value.draft = False
            return g
        with self.mock_config():
            result = repin_existing_projects(
                max_projects=2, rotation_slot=0,
                project_fetcher=fetch, control_fetcher=fetch,
                github_factory=factory, rpc=lambda _, body: receipt(body))
        self.assertEqual(result["status"], "completed_with_deferrals")
        self.assertEqual([r["status"] for r in result["results"]], ["deferred", "updated"])
        with self.mock_config():
            result = repin_existing_projects(
                max_projects=1, rotation_slot=0,
                project_fetcher=project_fetcher([first]),
                control_fetcher=project_fetcher([first]),
                github_factory=factory, rpc=lambda _, body: receipt(body))
        self.assertEqual(result["status"], "deferred")

    def test_draft_and_missing_pr_draft_metadata_fail_closed(self):
        policy = self.policy()
        for draft in (True, None):
            g = github(policy.target.repository)
            g.get_pull_request.return_value.draft = draft
            with self.subTest(draft=draft), self.assertRaisesRegex(PermissionError, "draft"):
                verify_candidate(g, target=policy.target, ci_policy=policy.ci, new_sha=NEW)

    def test_pr_or_branch_drift_after_ci_blocks_repin_before_rpc(self):
        item = project()
        for actor in ("branch", "pr"):
            g = github(item["repository"])
            if actor == "branch":
                g.get_branch_sha.side_effect = [NEW, NEW, OLD]
            else:
                valid = g.get_pull_request.return_value
                g.get_pull_request.side_effect = [
                    valid, SimpleNamespace(**{**vars(valid), "head_sha": OLD})]
            rpc = MagicMock()
            with self.subTest(actor=actor), self.assertRaisesRegex(PermissionError, "after exact-SHA"):
                repin_project(item, github_factory=lambda _: g, rpc=rpc)
            rpc.assert_not_called()

    def test_retry_same_number_attempt_different_id_is_ambiguous(self):
        policy = self.policy()
        g = github(policy.target.repository)
        row = g._call.return_value["workflow_runs"][0]
        g._call.return_value = {"total_count": 2, "workflow_runs": [
            row, {**row, "id": 100}
        ]}
        with self.assertRaisesRegex(PermissionError, "ambiguous"):
            verify_candidate(g, target=policy.target, ci_policy=policy.ci, new_sha=NEW)

    def test_version_zero_is_legal_same_as_installed_cas_rpc(self):
        p = project()
        p["execution_control"]["version"] = 0
        actual = repin_project(p, github_factory=github,
                               rpc=lambda _name, body: receipt(body))
        self.assertEqual(actual["version"], 1)
        p["execution_control"]["version"] = -1
        with self.assertRaisesRegex(PermissionError, "execution control"):
            repin_project(p, github_factory=github,
                          rpc=lambda _name, body: receipt(body))

    def test_wrong_rpc_receipt_must_never_report_updated(self):
        p = project()
        good = receipt({"p_project_key": "crm-infodive", "p_expected_sha": OLD,
                        "p_new_sha": NEW, "p_expected_generation": 6, "p_expected_version": 9})
        for wrong in ({"status": "updated"}, {"status": "noop"},
                      {**good, "project_key": "other"}, {**good, "new_sha": OLD},
                      {**good, "generation": 6}, {**good, "version": 9}):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(RuntimeError, "receipt"):
                repin_project(p, github_factory=github,
                              rpc=lambda _name, _body: wrong)

    def test_legacy_without_policy_does_not_consume_enabled_capacity(self):
        projects = [project(f"a-disabled-{i:02d}", f"owner/disabled-{i:02d}") for i in range(7)]
        for p in projects:
            del p["manifest"]["delivery_target"]["repin_policy"]
        projects.extend(project(f"b-eligible-{i:02d}", f"owner/eligible-{i:02d}")
                        for i in range(4))
        visited = []
        fetch = project_fetcher(projects)
        with self.mock_config():
            result = repin_existing_projects(
                max_projects=3, rotation_slot=0, project_fetcher=fetch, control_fetcher=fetch,
                github_factory=lambda repo: visited.append(repo) or github(repo),
                rpc=lambda _name, body: receipt(body))
        self.assertEqual(result["scanned"], 11)
        self.assertEqual(result["eligible"], 4)
        self.assertEqual(result["policy_disabled"], 7)
        self.assertEqual(result["total_groups"], 2)
        self.assertEqual(len(visited), 3)
        self.assertTrue(all("eligible" in repo for repo in visited))

    def test_policy_enabled_many_projects_rotate_without_starvation(self):
        projects = [project(f"candidate-{i:02d}", f"owner/candidate-{i:02d}")
                    for i in range(24)]
        visited = []
        fetch = project_fetcher(projects)
        with self.mock_config():
            for cycle in range(8):
                result = repin_existing_projects(
                    max_projects=3, rotation_slot=cycle,
                    project_fetcher=fetch, control_fetcher=fetch,
                    github_factory=lambda repo: visited.append(repo) or github(repo),
                    rpc=lambda _name, body: receipt(body))
                self.assertEqual(len(result["results"]), 3)
                self.assertEqual(result["scanned"], 24)
                self.assertEqual(result["eligible"], 24)
                self.assertEqual(result["total_groups"], 8)
        self.assertEqual(len(visited), 24)
        self.assertEqual(len(set(visited)), 24)

    def test_oversized_inventory_fails_closed_not_partial_selection(self):
        projects = [project(f"project-{i:03d}", f"owner/project-{i:03d}")
                    for i in range(101)]
        with self.mock_config(), self.assertRaisesRegex(RuntimeError, "exceeds bounded"):
            repin_existing_projects(max_projects=3, rotation_slot=0,
                                    project_fetcher=project_fetcher(projects))

    def test_all_policy_disabled_is_safe_idle(self):
        projects = [project("crm-infodive", "owner/crm")]
        del projects[0]["manifest"]["delivery_target"]["repin_policy"]
        with self.mock_config():
            result = repin_existing_projects(max_projects=3, rotation_slot=0,
                                             project_fetcher=project_fetcher(projects),
                                             github_factory=lambda _: self.fail("unexpected GitHub access"))
        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["policy_disabled"], 1)
        self.assertFalse(result["results"])

    def test_cli_reports_partial_failure_after_bounded_batch(self):
        import contextlib
        import io
        import json
        from ai_product_factory import runtime_cli
        for status, expected in (("idle", 0), ("completed", 0), ("partial_failure", 2)):
            with patch("sys.argv", ["factory-runtime", "--mode", "candidate-repin"]):
                with patch.object(runtime_cli, "repin_existing_projects",
                                  return_value={"status": status, "results": []}):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        code = runtime_cli.main()
            with self.subTest(status=status):
                self.assertEqual(code, expected)
                self.assertEqual(json.loads(output.getvalue())["status"], status)

    def test_repin_never_claims_paid_release_or_merge(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        script = (root / "src/ai_product_factory/nonproduction_candidate_repin.py").read_text()
        sql = (root / "supabase/migrations/20261019031000_repin_nonproduction_target.sql").read_text()
        workflow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        for forbidden in ("OPENAI_API_KEY", "merge_pull_request", "mark_released", "workflow_dispatch("):
            self.assertNotIn(forbidden, script)
        self.assertNotIn("crm-infodive", script)
        self.assertNotIn("CRM validation", script)
        for required in ("for update", "generation=generation+1", "project.delivery_target.reconciled",
                         "factory_control_quiescent", "from public,anon,authenticated", "to service_role"):
            self.assertIn(required, sql)
        self.assertIn("--mode candidate-repin --max-items 3", workflow)
        self.assertNotIn("--project-key crm-infodive", workflow)


if __name__ == "__main__":
    unittest.main()
