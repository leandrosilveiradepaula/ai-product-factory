"""Adversarial offline checks for rotation after an actual human merge."""
from __future__ import annotations

from dataclasses import dataclass, replace
import unittest
from unittest.mock import Mock

from ai_product_factory.released_existing_candidate import (
    attest_merged_source_rotation, rotate_released_project,
)

REPO = "leandrosilveiradepaula/crm-infodive"
OLD = "a" * 40
MERGE = "b" * 40
MAIN = "c" * 40
NEW = "d" * 40
BRANCH = "preview/crm22-admin-audit-next"
TICK = chr(96)
TASK = (
    "# CURRENT_TASK\n\n"
    "## Tarefa autorizada — CRM issue #22 — source bootstrap\n"
    "Origem: https://github.com/leandrosilveiradepaula/crm-infodive/issues/22\n"
    "Corrigir somente falha demonstrada de atualização administrativa sem efeito.\n"
    "Escopo de implementação futuro:\n- " + TICK +
    "src/app/(dashboard)/settings/users-actions.ts" + TICK + "\n- " + TICK +
    "src/lib/admin-audit.ts" + TICK + "\n- " + TICK +
    "test/server-admin-actions-rbac.test.ts" + TICK +
    "\nNão há implementação neste commit de fonte. Factory cria Work Units.\n"
)

@dataclass
class PR:
    number: int
    head_sha: str
    head_ref: str
    base_sha: str
    state: str = "open"
    merged: bool = False
    draft: bool = False
    head_repository: str = REPO
    base_ref: str = "main"
    merge_commit_sha: str | None = None


class Github:
    repository = REPO
    def __init__(self):
        self.old = PR(202, OLD, "preview/crm22-rbac-security-evidence", "e"*40,
                      state="closed", merged=True, merge_commit_sha=MERGE)
        self.new = PR(204, NEW, BRANCH, MAIN)
        self.main = MAIN
        self.branch = NEW
        self.doc = TASK
        self.changed = ("docs/codex/CURRENT_TASK.md",)
        self.rows = [
            {"id": 4100, "workflow_id": 372542929, "run_number": 100,
             "run_attempt": 1, "head_sha": NEW, "head_branch": BRANCH,
             "path": ".github/workflows/crm-validation.yml",
             "name": "CRM validation", "event": "pull_request",
             "status": "completed", "conclusion": "success"},
        ]
        self.source_paths = (
            "docs/codex/CURRENT_TASK.md",
            "src/app/(dashboard)/settings/users-actions.ts",
            "src/lib/admin-audit.ts",
            "test/server-admin-actions-rbac.test.ts",
        )

    def get_pull_request(self, number):
        return {202:self.old,204:self.new}[number]

    def get_branch_sha(self, branch):
        if branch == "main": return self.main
        if branch == BRANCH: return self.branch
        raise AssertionError("old merged branch must not be read")

    def compare_commits(self, before, after):
        if (before,after)==(MERGE,MAIN):
            return {"status":"ahead","behind_by":0,"ahead_by":1}
        if (before,after)==(MAIN,NEW):
            return {"status":"ahead","behind_by":0,"ahead_by":1}
        raise AssertionError("unexpected compare")

    def get_pull_request_files(self, number):
        assert number == 204
        return self.changed

    def get_file_text(self, path, *, ref):
        assert ref == NEW
        if path=="docs/codex/CURRENT_TASK.md": return self.doc
        assert path in self.source_paths
        return "export const observed = true;\n"

    def list_file_paths(self, *, ref):
        assert ref == NEW
        return self.source_paths

    def _call(self, method, path, *, query=None):
        assert method == "GET"
        if path.endswith("/pulls/204"):
            return {"body": "CRM issue #22 source-only Bootstrap, not release."}
        assert path.endswith("/actions/runs")
        assert query == {"head_sha":NEW,"per_page":"100"}
        return {"total_count":len(self.rows),"workflow_runs":self.rows}


def project():
    return {
        "id":"2d30e00a-ff72-4044-b838-011c263ed672",
        "project_key":"crm-infodive","repository":REPO,
        "project_kind":"existing","is_active":True,
        "execution_control":{"state":"running","generation":15,"version":14},
        "manifest":{
            "continuation_request":{
                "source":"github-owner","id":"request-22",
                "summary":"Concluir as pendências reais da issue #22 do CRM Infodive",
                "github":{
                    "repository":"leandrosilveiradepaula/ai-product-factory",
                    "issue_number":1055,"actor_id":256917842,
                },
            },
            "delivery_target":{
                "schema_version":1,"mode":"open_pr_candidate",
                "repository":REPO,
                "branch":"preview/crm22-rbac-security-evidence",
                "sha":OLD,"candidate_pr_number":202,
                "repin_policy":{
                    "enabled":True,"schema_version":1,
                    "native_ci":{
                        "schema_version":1,"event":"pull_request",
                        "workflow_id":372542929,
                        "workflow_name":"CRM validation",
                        "workflow_path":".github/workflows/crm-validation.yml",
                    },
                },
            },
        },
    }


class RotationTests(unittest.TestCase):
    def attest(self, github=None, project_row=None):
        return attest_merged_source_rotation(
            github or Github(),project=project_row or project(),
            candidate_pr_number=204,issue_number=22,
        )

    def test_merged_source_and_exact_native_ci(self):
        proof=self.attest()
        self.assertTrue(proof["old_merged"])
        self.assertEqual(proof["old_merge_sha"],MERGE)
        self.assertEqual(proof["pr_base_sha"],MAIN)
        self.assertEqual(proof["new_sha"],NEW)
        self.assertEqual(proof["ci_run_id"],4100)
        self.assertTrue(proof["source_only_candidate"])
        self.assertEqual(proof["source_scoped_file_count"],3)

    def test_old_missing_branch_is_not_required(self):
        self.assertEqual(self.attest()["old_pr_number"],202)

    def test_old_open_or_unmerged_refused(self):
        for change in ({"state":"open"},{"merged":False},
                       {"merge_commit_sha":None},{"head_sha":NEW},
                       {"head_repository":"other/repo"},{"base_ref":"dev"},
                       {"draft":True},{"head_ref":"preview/different"}):
            with self.subTest(change=change):
                gh=Github()
                gh.old=replace(gh.old,**change)
                with self.assertRaises(PermissionError): self.attest(gh)

    def test_old_merge_must_be_in_current_main(self):
        gh=Github()
        original=gh.compare_commits
        def changed(a,b):
            if (a,b)==(MERGE,MAIN):
                return {"status":"diverged","ahead_by":3,"behind_by":1}
            return original(a,b)
        gh.compare_commits=changed
        with self.assertRaises(PermissionError): self.attest(gh)

    def test_new_branch_behind_or_draft_or_fork_refused(self):
        for change in ({"draft":True},{"state":"closed"},{"merged":True},
                       {"head_repository":"fork/repo"},
                       {"head_sha":OLD},{"head_ref":"main"},
                       {"base_sha":"f"*40}):
            with self.subTest(change=change):
                gh=Github()
                gh.new=replace(gh.new,**change)
                with self.assertRaises(PermissionError): self.attest(gh)

    def test_source_only_governance_does_not_accept_product_code_changes(self):
        for files in (("docs/codex/CURRENT_TASK.md","src/lib/admin-audit.ts"),
                      ("docs/OTHER.md",),("src/lib/admin-audit.ts",),()):
            with self.subTest(files=files):
                gh=Github()
                gh.changed=files
                with self.assertRaises(PermissionError): self.attest(gh)

    def test_wrong_issue_and_empty_source_refused(self):
        for value in ("https://github.com/leandrosilveiradepaula/crm-infodive/issues/23",
                      "No active source paths.", ""):
            with self.subTest(value=value):
                gh=Github()
                gh.doc=value
                with self.assertRaises(PermissionError): self.attest(gh)

    def test_missing_test_source_path_refused(self):
        gh=Github()
        gh.source_paths=gh.source_paths[:-1]
        with self.assertRaises(PermissionError): self.attest(gh)

    def test_native_ci_failed_or_incorrect_is_denied(self):
        for change in ({"conclusion":"failure"},{"status":"in_progress"},
                       {"workflow_id":1},{"head_branch":"other"},
                       {"head_sha":"f"*40},{"event":"push"}):
            with self.subTest(change=change):
                gh=Github()
                gh.rows[0]={**gh.rows[0],**change}
                with self.assertRaises(PermissionError): self.attest(gh)

    def test_forged_owner_request_refused(self):
        for key,value in (("source","operator"),("summary","issue #23"),
                          ("id","")):
            with self.subTest(key=key):
                p=project()
                p["manifest"]["continuation_request"][key]=value
                with self.assertRaises(PermissionError): self.attest(project_row=p)
        p=project()
        p["manifest"]["continuation_request"]["github"]["actor_id"]=1
        with self.assertRaises(PermissionError): self.attest(project_row=p)

    def test_source_identity_drift_after_ci_refused(self):
        gh=Github()
        original=gh.get_pull_request
        seen=[0]
        def changed(number):
            if number==204:
                seen[0]+=1
                if seen[0]>=2:return replace(gh.new,head_sha="e"*40)
            return original(number)
        gh.get_pull_request=changed
        with self.assertRaises(PermissionError): self.attest(gh)

    def test_control_epoch_not_ready_does_not_call_rpc(self):
        for control in ({"state":"stopped","generation":15,"version":14},
                        {"state":"running","generation":True,"version":14},
                        {"state":"running","generation":15,"version":-1}):
            with self.subTest(control=control):
                p=project()
                p["execution_control"]=control
                rpc=Mock()
                with self.assertRaises(PermissionError):
                    rotate_released_project(p,candidate_pr_number=204,
                                            issue_number=22,rpc=rpc)
                rpc.assert_not_called()

    def test_atomic_cas_receipt_and_no_release_side_effect(self):
        calls=[]
        def rpc(name,params):
            calls.append((name,params))
            return {
                "status":"replaced","project_key":"crm-infodive",
                "old_sha":OLD,"new_sha":NEW,
                "old_pr_number":202,"new_pr_number":204,
                "generation":16,"version":15,
            }
        receipt=rotate_released_project(
            project(),candidate_pr_number=204,issue_number=22,
            github_factory=lambda repo:Github(),rpc=rpc,
        )
        self.assertEqual(receipt["status"],"source_candidate_rotated")
        self.assertFalse(receipt["factory_run_created"])
        self.assertEqual(receipt["old_merge_sha"],MERGE)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],"factory_replace_nonproduction_candidate_v1")
        params=calls[0][1]
        self.assertEqual(params["p_expected_generation"],15)
        self.assertEqual(params["p_expected_version"],14)
        self.assertEqual(params["p_actor_ref"],"factory-released-source-rotation")
        self.assertTrue(params["p_evidence"]["source_only_candidate"])

    def test_invalid_receipt_does_not_claim_success(self):
        with self.assertRaises(RuntimeError):
            rotate_released_project(
                project(),candidate_pr_number=204,issue_number=22,
                github_factory=lambda repo:Github(),
                rpc=lambda *args:{"status":"updated"},
            )


if __name__ == "__main__":
    unittest.main()
