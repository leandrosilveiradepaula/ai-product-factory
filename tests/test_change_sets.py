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
        store.frozen_source_commit.return_value=None
        store.bind_source.return_value=ChangeSetBinding("cs","wu","base","base","factory/change-set-cs",1)
        store.context_source.return_value={
            "project_key":"demo","repository":"owner/repo","change_set_id":"cs","work_unit_id":"wu",
            "plan_task_key":"a","agent_key":"development","wave":1,
            "task":{"title":"A","description":"desc","acceptance_criteria":[]},
            "assignment":{"task_key":"a","agent_key":"development","scope_keys":["src/a.py"],"required_capabilities":["implementation"],"depends_on":[]},
            "repair":{},"constraints":[],
        }
        producer=MagicMock()
        producer.produce.return_value=ImplementationArtifact(
            "plan",{"src/a.py":"value=1"},"feat: a","unused title","unused body"
        )
        item=DirectExecutionItem(
            "run","task","demo","owner/repo",None,"A","desc","factory/cs/a",False,"cs","wu",1
        )
        impact=MagicMock();impact.analyze_run.return_value=SimpleNamespace(as_context=lambda:{"confidence":"high","impacted_nodes":[],"unknowns":[]})
        provenance=MagicMock()
        result=ChangeSetBuilderWorker(github=github,store=store,producer=producer,impact_engine=impact,provenance=provenance).execute(item)
        self.assertEqual(result.output_commit,"out")
        github.ensure_branch_at_sha.assert_called_once_with("factory/cs/a","base")
        github.commit_files.assert_called_once()
        message=github.commit_files.call_args.kwargs["message"]
        self.assertIn("Factory-Run: run",message)
        self.assertIn("Factory-Change-Set: cs",message)
        self.assertIn("Factory-Work-Unit: wu",message)
        self.assertIn("Factory-Agent: development",message)
        self.assertIn("Factory-Context-SHA256: ",message)
        self.assertNotIn('"objective"',message)
        self.assertFalse(github.create_pull_request.called)
        store.complete_work_unit.assert_called_once_with(
            run_id="run",output_commit="out",changed_files=("src/a.py",)
        )
        impact.analyze_run.assert_called_once()
        produced=producer.produce.call_args.args[0]
        self.assertEqual(produced.impact_context["confidence"],"high")
        self.assertEqual(produced.base_commit,"base")
        self.assertEqual(produced.write_scopes,("src/a.py",))
        self.assertEqual(produced.context_packet["work_unit"]["task_key"],"a")
        store.record_context.assert_called_once()
        provenance.record.assert_called_once()


    def test_builder_retry_uses_frozen_change_set_source_instead_of_new_main(self):
        github=MagicMock()
        github.get_branch_sha.return_value="new-main"
        github.commit_files.return_value="out"
        store=MagicMock()
        store.frozen_source_commit.return_value="frozen-base"
        store.bind_source.return_value=ChangeSetBinding("cs","wu","frozen-base","frozen-base","factory/change-set-cs",1)
        store.context_source.return_value={
            "project_key":"demo","repository":"owner/repo","change_set_id":"cs","work_unit_id":"wu",
            "plan_task_key":"a","agent_key":"development","wave":1,
            "task":{"title":"A","description":"desc","acceptance_criteria":[]},
            "assignment":{"task_key":"a","agent_key":"development","scope_keys":["src/a.py"],"required_capabilities":["implementation"],"depends_on":[]},
            "repair":{},"constraints":[],
        }
        producer=MagicMock()
        producer.produce.return_value=ImplementationArtifact("plan",{"src/a.py":"value=1"},"feat: a","unused","unused")
        item=DirectExecutionItem("run","task","demo","owner/repo",None,"A","desc","factory/cs/a",False,"cs","wu",1)
        impact=MagicMock();impact.analyze_run.return_value=SimpleNamespace(as_context=lambda:{"confidence":"high","impacted_nodes":[],"unknowns":[]})
        ChangeSetBuilderWorker(github=github,store=store,producer=producer,impact_engine=impact,provenance=MagicMock()).execute(item)
        store.frozen_source_commit.assert_called_once_with("cs")
        store.bind_source.assert_called_once_with(
            run_id="run",source_commit="frozen-base",integration_branch="factory/change-set-cs",work_branch="factory/cs/a"
        )
        github.ensure_branch_at_sha.assert_called_once_with("factory/cs/a","frozen-base")

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
        integration_message=github.commit_files.call_args.kwargs["message"]
        self.assertIn("Factory-Change-Set: cs12345678",integration_message)
        self.assertIn("Factory-Wave: 1",integration_message)
        store.prepare_release.assert_called_once()
        store.mark_repair_wave_integrated.assert_called_once_with(
            change_set_id="cs12345678",wave=1,candidate_commit="integrated"
        )
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
