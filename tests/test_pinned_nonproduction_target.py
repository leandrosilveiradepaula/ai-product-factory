import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.pinned_nonproduction_target import PinnedNonproductionTarget
from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.change_set_integrator import ChangeSetIntegrator
from ai_product_factory.change_set_store import ChangeSetIntegrationItem
from ai_product_factory.execution_worker import DirectExecutionItem


SHA = "f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e"
TARGET = {"schema_version": 1, "mode": "open_pr_candidate",
          "repository": "owner/crm",
          "branch": "preview/hardening-release-candidate",
          "sha": SHA, "candidate_pr_number": 56}


def github():
    g = MagicMock()
    g.repository = "owner/crm"
    g.get_branch_sha.return_value = SHA
    g.get_pull_request.return_value = SimpleNamespace(
        state="open", merged=False, head_sha=SHA,
        head_ref=TARGET["branch"], head_repository="owner/crm", base_ref="main")
    return g


class TargetTests(unittest.TestCase):
    def test_exact_open_nonproduction_candidate(self):
        target = PinnedNonproductionTarget.parse(TARGET, repository="owner/crm")
        target.verify(github())

    def test_invalid_policy_rejected(self):
        for mutation in (
            {"sha": "main"}, {"branch": "main"}, {"candidate_pr_number": True},
            {"repository": "other/repo"}, {"mode": "unrestricted"},
            {"branch": "preview/../main"},
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(PermissionError):
                    PinnedNonproductionTarget.parse({**TARGET, **mutation}, repository="owner/crm")

    def test_drift_and_closed_candidate_are_rejected(self):
        target = PinnedNonproductionTarget.parse(TARGET, repository="owner/crm")
        for attr, value in (("state", "closed"), ("merged", True), ("head_sha", "a" * 40),
                            ("head_ref", "main"), ("base_ref", "release"),
                            ("head_repository", "other/repo")):
            g = github()
            setattr(g.get_pull_request.return_value, attr, value)
            with self.subTest(attr=attr), self.assertRaises(PermissionError):
                target.verify(g)
        g = github()
        g.get_branch_sha.return_value = "a" * 40
        with self.assertRaises(PermissionError):
            target.verify(g)

    def test_builder_missing_target_prevents_bind_and_github_write(self):
        g = github()
        store = MagicMock()
        store.context_source.return_value = {
            "project_key": "crm", "repository": "owner/crm",
            "project_kind": "existing", "delivery_target": None}
        builder = ChangeSetBuilderWorker(
            github=g, store=store, producer=MagicMock(),
            impact_engine=MagicMock(), provenance=MagicMock())
        item = DirectExecutionItem(
            "run", "task", "crm", "owner/crm", None, "A", "B",
            "factory/cs/a", False, "cs", "wu", 1)
        with self.assertRaises(PermissionError):
            builder.execute(item)
        store.bind_source.assert_not_called()
        g.ensure_branch_at_sha.assert_not_called()
        g.commit_files.assert_not_called()

    def test_integrator_rejects_unpinned_existing_project_without_writes(self):
        g = github()
        store = MagicMock()
        item = ChangeSetIntegrationItem(
            "cs", "crm", "owner/crm", SHA, "candidate",
            "factory/change-set-cs", 1,
            ({"plan_task_key": "a", "base_commit": "candidate",
              "output_commit": "output", "changed_files": ["src/a.py"]},),
            project_kind="existing", delivery_target=None)
        with self.assertRaises(PermissionError):
            ChangeSetIntegrator(github=g, store=store).integrate(item)
        g.ensure_branch_at_sha.assert_not_called()
        g.create_pull_request.assert_not_called()

    def test_integration_uses_pinned_base_not_main(self):
        g = github()
        g.get_file_text.return_value = "value=1"\n        g.get_branch_sha.side_effect = lambda ref: SHA if ref == TARGET["branch"] else "integrated"
        g.commit_files.return_value = "integrated"
        g.find_open_issue_containing.return_value = SimpleNamespace(
            number=9, html_url="https://example.test/issues/9")
        g.find_open_pull_request_containing.return_value = None
        g.create_pull_request.return_value = SimpleNamespace(
            number=12, head_sha="integrated", base_ref=TARGET["branch"])
        store = MagicMock()
        store.complete_integration.return_value = {
            "status": "review_ready", "change_set_id": "cs",
            "candidate_commit": "integrated", "current_wave": 1,
            "repair_jobs_integrated": 0}
        store.prepare_release.return_value = {
            "status": "ci_pending", "change_set_id": "cs",
            "release_run_id": "release"}
        item = ChangeSetIntegrationItem(
            "cs", "crm", "owner/crm", SHA, "candidate",
            "factory/change-set-cs", 1,
            ({"plan_task_key": "a", "base_commit": "candidate",
              "output_commit": "output", "changed_files": ["src/a.py"]},),
            project_kind="existing", delivery_target=TARGET)
        ChangeSetIntegrator(github=g, store=store).integrate(item)
        self.assertEqual(g.create_pull_request.call_args.kwargs["base"], TARGET["branch"])


if __name__ == "__main__":
    unittest.main()
