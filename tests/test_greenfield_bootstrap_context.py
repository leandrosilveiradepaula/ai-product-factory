"""README-only greenfield bootstrap is intentionally narrow and verifiable.

No network calls: exercised through ChangeSetBuilderWorker with a frozen
source commit and a deterministic producer. The same context builder handles
both CRM fixes and new product bootstraps without global root write scope.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.change_set_store import ChangeSetBinding
from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.execution_worker import (
    DirectExecutionItem, ImplementationArtifact,
)
from ai_product_factory.work_unit_context import enforce_write_scopes


SCOPES=[
    "application-foundation","database-migrations",
    "environment-template","domain-shared",
]


def source(*,wave=1,key="foundation-app",scopes=None,explicit=None):
    assignment={
        "scope_keys":list(SCOPES if scopes is None else scopes),
        "required_capabilities":["implementation"],
        "depends_on":[],
    }
    if explicit is not None:
        assignment["context_paths"]=list(explicit)
    return {
        "project_key":"new-support-product",
        "repository":"owner/new-support-product",
        "plan_task_key":key,
        "agent_key":"development",
        "wave":wave,
        "task":{
            "title":"Fundacao da aplicacao",
            "description":None,
            "acceptance_criteria":[
                "TypeScript code split into modules",
                "Versioned database migrations",
                "Central environment configuration validation",
                "Unit tests for shared helpers",
            ],
        },
        "assignment":assignment,
        "repair":{},
        "constraints":["No production merge","Do not expose credentials"],
    }


def fixture(*,repository_paths=("README.md",),source_value=None,artifact_files=None):
    gh=MagicMock()
    gh.get_branch_sha.return_value="source-commit"
    gh.list_file_paths.return_value=tuple(repository_paths)
    gh.get_file_text.side_effect=lambda path,ref: {
        "README.md":"# new-support-product\n",
        "AGENTS.md":"Governance: no production merge.\n",
    }.get(path,"test context\n")
    gh.commit_files.return_value="artifact-commit"

    store=MagicMock()
    store.frozen_source_commit.return_value="source-commit"
    store.bind_source.return_value=ChangeSetBinding(
        "cs","wu","source-commit","source-commit",
        "factory/change-set-cs",1,
    )
    store.context_source.return_value=source() if source_value is None else source_value

    prod=MagicMock()
    prod.produce.return_value=ImplementationArtifact(
        "Initial TypeScript foundation",
        artifact_files or {
            "package.json":'{"type":"module"}\n',
            "src/domain/support.ts":"export type Ticket = { id: string };\n",
            "supabase/migrations/001_initial.sql":"-- versioned migration\n",
            "tests/support.test.ts":"// deterministic unit test\n",
        },
        "feat: initialize application foundation","Foundation","Bootstrap",
    )
    impact=MagicMock()
    impact.analyze_run.return_value=SimpleNamespace(
        as_context=lambda:{"confidence":"high","impacted_nodes":[],"unknowns":[]},
    )
    worker=ChangeSetBuilderWorker(
        github=gh,store=store,producer=prod,
        impact_engine=impact,provenance=MagicMock(),
    )
    item=DirectExecutionItem(
        "run","task","new-support-product","owner/new-support-product",
        None,"Foundation","","factory/cs/foundation",
        False,"cs","wu",1,
    )
    return worker,item,gh,store,prod


class GreenfieldContextTests(unittest.TestCase):
    def test_readme_only_first_wave_scaffolds_with_bounded_scopes(self):
        worker,item,gh,store,prod=fixture()
        result=worker.execute(item)
        self.assertEqual(result.output_commit,"artifact-commit")
        gh.list_file_paths.assert_called_once_with(ref="source-commit")
        gh.get_file_text.assert_called_once_with("README.md",ref="source-commit")
        snapshot=prod.produce.call_args.args[0].context_packet
        self.assertEqual(
            snapshot["repository_snapshot"],
            {"README.md":"# new-support-product\n"},
        )
        scopes=snapshot["repository"]["write_scopes"]
        self.assertIn("src/**",scopes)
        self.assertIn("supabase/migrations/**",scopes)
        self.assertIn("package.json",scopes)
        self.assertNotIn(".",scopes)
        self.assertNotIn("README.md",scopes)
        for forbidden in (
            ".github/workflows/enable-prod.yml",
            ".env","service-role-key.txt","secrets/api.txt",
        ):
            with self.subTest(forbidden=forbidden),self.assertRaises(PermissionError):
                enforce_write_scopes([forbidden],scopes)
        store.complete_work_unit.assert_called_once()

    def test_governance_read_before_greenfield_scaffold(self):
        worker,item,gh,store,prod=fixture(
            repository_paths=("README.md","AGENTS.md"),
        )
        worker.execute(item)
        self.assertEqual(
            prod.produce.call_args.args[0].context_packet["repository_snapshot"],
            {
                "AGENTS.md":"Governance: no production merge.\n",
                "README.md":"# new-support-product\n",
            },
        )

    def test_rejects_arbitrary_task_or_later_wave(self):
        for candidate in (
            source(key="billing-hotfix"),
            source(wave=2),
            source(scopes=["application-foundation","unknown-billing-access"]),
            source(scopes=["domain-shared"]),
        ):
            with self.subTest(candidate=candidate):
                worker,item,gh,store,prod=fixture(source_value=candidate)
                with self.assertRaises(RuntimeError):
                    worker.execute(item)
                prod.produce.assert_not_called()
                gh.commit_files.assert_not_called()
                store.block_work_unit.assert_called_once()

    def test_populated_repository_requires_real_relevant_context(self):
        worker,item,gh,store,prod=fixture(
            repository_paths=("README.md","src/core.ts"),
        )
        with self.assertRaisesRegex(RuntimeError,"no relevant files"):
            worker.execute(item)
        prod.produce.assert_not_called()

    def test_missing_readme_does_not_enable_blank_context(self):
        worker,item,gh,store,prod=fixture(repository_paths=())
        with self.assertRaisesRegex(RuntimeError,"no relevant files"):
            worker.execute(item)
        prod.produce.assert_not_called()

    def test_explicit_context_is_never_overridden_by_bootstrap_rule(self):
        candidate=source(explicit=["../secrets"])
        worker,item,gh,store,prod=fixture(source_value=candidate)
        with self.assertRaisesRegex(ValueError,"invalid repository context path"):
            worker.execute(item)
        prod.produce.assert_not_called()

    def test_scaffold_model_cannot_write_github_workflow(self):
        worker,item,gh,store,prod=fixture(
            artifact_files={".github/workflows/unsafe.yml":"on: push\n"},
        )
        with self.assertRaisesRegex(PermissionError,"outside assigned scopes"):
            worker.execute(item)
        gh.commit_files.assert_not_called()
        store.complete_work_unit.assert_not_called()
        store.block_work_unit.assert_called_once()
        self.assertEqual(
            store.block_work_unit.call_args.kwargs["blocker_type"],
            "repository_governance",
        )


if __name__=="__main__":
    unittest.main()
