"""B3: trusted newest capture survives code-only main merges, never forged reuse."""
from __future__ import annotations

import copy
import unittest

from ai_product_factory.independent_authenticated_console_evidence import (
    AuthenticatedConsoleEvidenceBlocked,
    verify_reusable_latest_authenticated_console_evidence,
)

REPO = "leandrosilveiradepaula/ai-product-factory"
SOURCE = "a" * 40
TARGET = "b" * 40
RUN = 12345678
PREFIX = "/repos/" + REPO
LATEST = (
    "factory_visual_evidence_runs?select=workflow_run_id,source_commit,artifact_name,status"
    "&status=eq.captured&order=created_at.desc&limit=1"
)
EXACT = (
    "factory_visual_evidence_runs?select=workflow_run_id,source_commit,artifact_name,status"
    "&workflow_run_id=eq." + str(RUN) + "&limit=2"
)
REGISTRY = {
    "workflow_run_id": RUN, "source_commit": SOURCE,
    "artifact_name": "authenticated-console-" + str(RUN), "status": "captured",
}


def data():
    tree = {"truncated": False, "tree": [
        {"type": "tree", "path": "apps/console/app", "mode": "040000", "sha": "c" * 40},
        {"type": "blob", "path": "apps/console/app/page.tsx",
         "mode": "100644", "sha": "d" * 40},
    ]}
    return {
        PREFIX: {"default_branch": "main"},
        PREFIX + "/git/ref/heads/main": {"object": {"sha": TARGET}},
        PREFIX + "/actions/runs/" + str(RUN): {
            "id": RUN, "name": "Authenticated Console visual evidence",
            "path": ".github/workflows/authenticated-visual-evidence.yml",
            "event": "push", "head_branch": "main", "head_sha": SOURCE,
            "run_attempt": 1, "status": "completed", "conclusion": "success",
            "repository": {"full_name": REPO},
        },
        PREFIX + "/actions/runs/" + str(RUN) + "/jobs?per_page=100": {
            "total_count": 1,
            "jobs": [{"name": "capture", "run_id": RUN, "head_sha": SOURCE,
                      "status": "completed", "conclusion": "success"}],
        },
        PREFIX + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100": {
            "total_count": 1,
            "artifacts": [{
                "id": 56, "name": "authenticated-console-" + str(RUN),
                "expired": False, "size_in_bytes": 100,
                "workflow_run": {"id": RUN, "head_sha": SOURCE,
                                 "head_branch": "main"},
            }],
        },
        PREFIX + "/compare/" + SOURCE + "..." + TARGET: {
            "status": "ahead", "behind_by": 0,
            "base_commit": {"sha": SOURCE},
            "merge_base_commit": {"sha": SOURCE},
        },
        PREFIX + "/git/trees/" + SOURCE + "?recursive=1": tree,
        PREFIX + "/git/trees/" + TARGET + "?recursive=1": copy.deepcopy(tree),
    }


class RecentB3SourceReuse(unittest.TestCase):
    def verify(self, github=None, latest=None, exact=None):
        docs = data() if github is None else github
        rows = [REGISTRY] if latest is None else latest
        exact_rows = [REGISTRY] if exact is None else exact
        requested = []
        def cp(path):
            requested.append(path)
            if path == LATEST:
                return rows
            if path == EXACT:
                return exact_rows
            raise AssertionError("unexpected source request")
        result = verify_reusable_latest_authenticated_console_evidence(
            repository=REPO, assessed_commit=TARGET,
            github_get=lambda path: docs[path], control_plane_get=cp,
        )
        self.assertEqual(requested, [LATEST, EXACT])
        return result

    def test_real_exact_source_tree_reused_for_new_unrelated_main_sha(self):
        result = self.verify()
        self.assertEqual(result.source_commit, SOURCE)
        self.assertEqual(result.assessed_commit, TARGET)
        self.assertEqual(result.workflow_run_id, RUN)
        self.assertEqual(result.artifact_id, 56)
        self.assertNotIn("product_ready", result.receipt().get("source", ""))
        self.assertIn("product_ready", result.receipt()["does_not_certify"])

    def test_latest_registry_missing_ambiguous_and_untrusted_never_falls_back(self):
        for source in ([], [REGISTRY, REGISTRY], [{}],
                       [{**REGISTRY, "artifact_name": "tampered"}],
                       [{**REGISTRY, "source_commit": "invalid"}],
                       [{**REGISTRY, "workflow_run_id": True}],
                       [{**REGISTRY, "status": "provisioned"}],
                       [{**REGISTRY, "secret": "not-allowed"}]):
            with self.subTest(source=source), self.assertRaises(AuthenticatedConsoleEvidenceBlocked):
                self.verify(latest=source)

    def test_exact_registry_conflict_blocks_replay(self):
        for source in ([], [REGISTRY, REGISTRY],
                       [{**REGISTRY, "status": "failed"}],
                       [{**REGISTRY, "source_commit": "f"*40}]):
            with self.subTest(source=source), self.assertRaises(AuthenticatedConsoleEvidenceBlocked):
                self.verify(exact=source)

    def test_reject_stale_run_rerun_unsafe_event_and_wrong_repository(self):
        run_path = PREFIX + "/actions/runs/" + str(RUN)
        for change in ({"run_attempt": 2}, {"event": "workflow_dispatch"},
                       {"conclusion": "failure"}, {"head_sha": "f"*40},
                       {"repository": {"full_name": "attacker/other"}}):
            docs = data()
            docs[run_path].update(change)
            with self.subTest(change=change), self.assertRaises(AuthenticatedConsoleEvidenceBlocked):
                self.verify(github=docs)

    def test_full_tree_and_ancestry_are_mandatory(self):
        for mutation in ("behind", "wrong_mergebase", "changed_console", "truncated"):
            docs = data()
            comp = docs[PREFIX + "/compare/" + SOURCE + "..." + TARGET]
            tree = docs[PREFIX + "/git/trees/" + TARGET + "?recursive=1"]
            if mutation == "behind":
                comp["behind_by"] = 1
            elif mutation == "wrong_mergebase":
                comp["merge_base_commit"]["sha"] = "f"*40
            elif mutation == "changed_console":
                tree["tree"][1]["sha"] = "e"*40
            else:
                tree["truncated"] = True
            with self.subTest(mutation=mutation), self.assertRaises(AuthenticatedConsoleEvidenceBlocked):
                self.verify(github=docs)

    def test_expired_or_missing_artifact_never_fabricates_browser_proof(self):
        docs = data()
        artifact = docs[PREFIX + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100"]
        artifact["artifacts"][0]["expired"] = True
        self.assertIsNone(self.verify(github=docs).artifact_id)
        artifact["artifacts"] = []
        artifact["total_count"] = 0
        self.assertIsNone(self.verify(github=docs).artifact_id)


if __name__ == "__main__":
    unittest.main()
