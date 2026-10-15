from __future__ import annotations

import copy
from pathlib import Path
import unittest
from ai_product_factory.existing_project_github_inventory import inventory_candidate
from ai_product_factory.existing_project_inventory import BaselineInventoryError
from ai_product_factory.release_intelligence import _verified_existing_baseline

R="example/crm"
SHA="a"*40
TREE="b"*40


def fixtures():
    p="/repos/"+R
    return {
        p:{"full_name":R,"default_branch":"main"},
        p+"/pulls/56":{"number":56,"state":"open",
            "head":{"sha":SHA,"repo":{"full_name":R}},
            "base":{"ref":"main","repo":{"full_name":R}}},
        p+"/git/commits/"+SHA:{"sha":SHA,"tree":{"sha":TREE}},
        p+"/git/trees/"+TREE+"?recursive=1":{
            "sha":TREE,"truncated":False,
            "tree":[{"type":"blob","mode":"100644","path":p} for p in (
                "src/app/page.tsx","tests/a.test.ts","docs/OPERATIONS.md",
                ".github/workflows/ci.yml","supabase/migrations/1.sql")]},
    }


class GithubExistingInventoryTests(unittest.TestCase):
    def check(self, changes=None):
        rows=fixtures()
        for path,change in (changes or {}).items():
            rows[path].update(change)
        calls=[]
        result=inventory_candidate(repository=R,candidate_sha=SHA,pr_number=56,
            get_json=lambda path:(calls.append(path) or copy.deepcopy(rows[path])))
        return result,calls

    def test_exact_pinned_tree_nonpassing(self):
        result,calls=self.check()
        self.assertEqual(len(calls),4)
        self.assertEqual(result["inventory"]["tracked_files"],5)
        self.assertEqual(result["inventory"]["migration_files"],1)
        self.assertEqual(result["inventory"]["workflow_files"],1)
        self.assertTrue(result["remote_identity_verified"])
        self.assertEqual(result["status"],"not_assessed")
        self.assertEqual(result["coverage"],["repository_inventory"])
        self.assertFalse(result["authenticated_journeys_verified"])
        self.assertFalse(result["production_schema_verified"])
        ok,_=_verified_existing_baseline(
            {"evaluation_status":"passed","baseline_ref":SHA,"result":result},SHA)
        self.assertFalse(ok)

    def test_wrong_target_or_closed_pr_fails(self):
        pr="/repos/"+R+"/pulls/56"
        for change in ({"state":"closed"},{"head":{"sha":"c"*40,"repo":{"full_name":R}}},
                       {"base":{"ref":"other","repo":{"full_name":R}}}):
            with self.subTest(change=change),self.assertRaises(BaselineInventoryError):
                self.check({pr:change})

    def test_incomplete_tree_rejected(self):
        p="/repos/"+R+"/git/trees/"+TREE+"?recursive=1"
        for change in ({"truncated":True},{"sha":"c"*40},{"tree":None}):
            with self.subTest(change=change),self.assertRaises(BaselineInventoryError):
                self.check({p:change})

    def test_symlinks_submodules_duplicates_and_paths_rejected(self):
        p="/repos/"+R+"/git/trees/"+TREE+"?recursive=1"
        cases=[
            [{"path":"a","type":"blob","mode":"120000"}],
            [{"path":"a","type":"commit","mode":"160000"}],
            [{"path":"a","type":"blob","mode":"100644"}]*2,
            [{"path":"../bad","type":"blob","mode":"100644"}],
        ]
        for entries in cases:
            with self.subTest(entries=entries),self.assertRaises(BaselineInventoryError):
                self.check({p:{"tree":entries}})

    def test_wrong_repository_and_commit_refused(self):
        with self.assertRaises(BaselineInventoryError):
            self.check({"/repos/"+R:{"full_name":"attacker/crm"}})
        with self.assertRaises(BaselineInventoryError):
            self.check({"/repos/"+R+"/git/commits/"+SHA:{"sha":"c"*40}})
        with self.assertRaises(BaselineInventoryError):
            inventory_candidate(repository="../crm",candidate_sha=SHA,pr_number=56,
                get_json=lambda _:self.fail("should not query untrusted repository"))

    def test_privileged_workflow_main_only(self):
        root=Path(__file__).resolve().parents[1]
        s=(root/".github/workflows/crm-cross-repo-preflight.yml").read_text()
        self.assertIn("branches: [main]",s)
        self.assertIn("./.github/actions/control-plane-oidc",s)
        self.assertNotIn("pull_request_target:",s)
        self.assertNotIn("issue_comment:",s)
        self.assertIn("Upload read-only inventory",s)
        self.assertIn('".github/crm-existing-inventory-target.json"',s)
        self.assertIn("inventory_candidate(",s)
        self.assertIn("get_json=lambda path: _get(token,path)",s)
        broker=(root/"supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        self.assertIn("crm-cross-repo-preflight.yml@refs/heads/main",broker)
        self.assertNotIn("crm-existing-inventory.yml@refs/heads/main",broker)
        self.assertNotIn("factory_evaluations",s)


if __name__=="__main__":
    unittest.main()
