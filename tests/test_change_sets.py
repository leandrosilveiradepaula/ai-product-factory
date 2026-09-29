import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.change_set_integrator import ChangeSetIntegrator
from ai_product_factory.change_set_store import ChangeSetBinding,ChangeSetIntegrationItem
from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.execution_worker import DirectExecutionItem,ImplementationArtifact


class ChangeSetTests(unittest.TestCase):
    def test_builder_commits_isolated_work_unit_without_pr(self):
        github=MagicMock()
        github.get_branch_sha.return_value="base"
        github.commit_files.return_value="out"
        store=MagicMock()
        store.bind_source.return_value=ChangeSetBinding("cs","wu","base","base","factory/change-set-cs",1)
        producer=MagicMock()
        producer.produce.return_value=ImplementationArtifact(
            "plan",{"src/a.py":"value=1"},"feat: a","unused title","unused body"
        )
        item=DirectExecutionItem(
            "run","task","demo","owner/repo",None,"A","desc","factory/cs/a",False,"cs","wu",1
        )
        result=ChangeSetBuilderWorker(github=github,store=store,producer=producer).execute(item)
        self.assertEqual(result.output_commit,"out")
        github.ensure_branch_at_sha.assert_called_once_with("factory/cs/a","base")
        github.commit_files.assert_called_once()
        self.assertEqual(producer.produce.call_args.args[0].base_commit,"base")
        self.assertFalse(github.create_pull_request.called)
        store.complete_work_unit.assert_called_once_with(
            run_id="run",output_commit="out",changed_files=("src/a.py",)
        )

    def test_integrator_rejects_overlapping_files(self):
        github=MagicMock()
        store=MagicMock()
        item=ChangeSetIntegrationItem(
            "cs","demo","owner/repo","base","base","factory/change-set-cs",1,(
                {"plan_task_key":"a","base_commit":"base","output_commit":"a1","changed_files":["src/shared.py"]},
                {"plan_task_key":"b","base_commit":"base","output_commit":"b1","changed_files":["src/shared.py"]},
            )
        )
        with self.assertRaisesRegex(RuntimeError,"file conflict"):
            ChangeSetIntegrator(github=github,store=store).integrate(item)
        github.commit_files.assert_not_called()
        store.complete_integration.assert_not_called()

    def test_integrator_creates_one_release_pr_for_final_candidate(self):
        github=MagicMock()
        github.get_file_text.side_effect=["A","B"]
        github.commit_files.return_value="integrated"
        github.find_open_issue_containing.return_value=None
        github.create_issue.return_value=SimpleNamespace(number=7,html_url="https://github/issue/7")
        github.find_open_pull_request_containing.return_value=None
        github.create_pull_request.return_value=SimpleNamespace(number=9,head_sha="integrated")
        store=MagicMock()
        store.complete_integration.return_value={"status":"review_ready","candidate_commit":"integrated"}
        item=ChangeSetIntegrationItem(
            "cs12345678","demo","owner/repo","base","base","factory/change-set-cs12345678",1,(
                {"plan_task_key":"a","base_commit":"base","output_commit":"a1","changed_files":["src/a.py"]},
                {"plan_task_key":"b","base_commit":"base","output_commit":"b1","changed_files":["src/b.py"]},
            )
        )
        result=ChangeSetIntegrator(github=github,store=store).integrate(item)
        self.assertEqual(result.status,"ci_pending")
        self.assertEqual(result.candidate_commit,"integrated")
        self.assertEqual(result.pull_request.number,9)
        github.create_pull_request.assert_called_once()
        store.prepare_release.assert_called_once()
        self.assertEqual(store.prepare_release.call_args.kwargs["candidate_commit"],"integrated")

    def test_integrator_requires_each_unit_to_share_current_base(self):
        github=MagicMock();store=MagicMock()
        item=ChangeSetIntegrationItem(
            "cs","demo","owner/repo","source","candidate","factory/change-set-cs",2,(
                {"plan_task_key":"a","base_commit":"old","output_commit":"out","changed_files":["src/a.py"]},
            )
        )
        with self.assertRaisesRegex(RuntimeError,"base commit"):
            ChangeSetIntegrator(github=github,store=store).integrate(item)


if __name__=="__main__":
    unittest.main()
