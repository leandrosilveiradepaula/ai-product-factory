"""Real Factory incident: platform Change Set handoff and optional no-cost recovery.

No OpenAI, GitHub network, project mutation or Production merge in these tests.
"""
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.change_set_integrator import ChangeSetIntegrator
from ai_product_factory.change_set_store import (
    ChangeSetBinding, ChangeSetIntegrationItem, SupabaseChangeSetStore,
)
from ai_product_factory.execution_worker import DirectExecutionItem, ImplementationArtifact

SHA = "a" * 40
NEXT = "b" * 40
OUTPUT = "c" * 40
REPO = "owner/platform-repo"
PATH = "scripts/audit_autonomy_journey.py"
ROOT = Path(__file__).resolve().parents[1]


def builder_fixture(*, kind="platform", frozen=None, main=SHA, target=None):
    github = MagicMock()
    github.repository = REPO
    github.get_branch_sha.return_value = main
    github.list_file_paths.return_value = (
        "AGENTS.md", "PROJECT_PLAN.md", PATH, "tests/test_autonomy_journey.py",
    )
    github.get_file_text.return_value = "def audit(): return True\n"
    github.commit_files.return_value = OUTPUT
    store = MagicMock()
    store.context_source.return_value = {
        "project_key": "platform-demo", "repository": REPO,
        "project_kind": kind, "delivery_target": target,
        "change_set_id": "cs", "work_unit_id": "wu",
        "plan_task_key": "DIAGNOSE", "agent_key": "development", "wave": 1,
        "task": {
            "title": "DIAGNOSE", "description": "Implement diagnosis",
            "acceptance_criteria": ["Reviewable deterministic implementation"],
        },
        "assignment": {
            "task_key": "DIAGNOSE", "agent_key": "development",
            "scope_keys": [PATH], "context_paths": [PATH],
            "required_capabilities": ["implementation"], "depends_on": [],
        },
        "repair": {}, "constraints": [],
    }
    store.frozen_source_commit.return_value = frozen
    store.bind_source.return_value = ChangeSetBinding(
        "cs", "wu", SHA, SHA, "factory/change-set-cs", 1
    )
    producer = MagicMock()
    producer.produce.return_value = ImplementationArtifact(
        "Plan", {PATH: "def audit(): return {'status': 'ok'}\n"},
        "feat: add verified journey diagnosis", "unused title", "unused body"
    )
    impact = MagicMock()
    impact.analyze_run.return_value = SimpleNamespace(
        as_context=lambda: {"confidence": "high", "impacted_nodes": [], "unknowns": []}
    )
    item = DirectExecutionItem(
        "run", "task", "platform-demo", REPO, None,
        "DIAGNOSE", "Implement diagnosis",
        "factory/cs/diagnose", False, "cs", "wu", 1
    )
    return github, store, producer, impact, item


class PlatformBuilderTests(unittest.TestCase):
    def test_explicit_platform_can_reach_real_producer_from_verified_main(self):
        github, store, producer, impact, item = builder_fixture()
        result = ChangeSetBuilderWorker(
            github=github, store=store, producer=producer,
            impact_engine=impact, provenance=MagicMock(),
        ).execute(item)
        self.assertEqual(result.output_commit, OUTPUT)
        github.get_branch_sha.assert_called_once_with("main")
        store.bind_source.assert_called_once_with(
            run_id="run", source_commit=SHA,
            integration_branch="factory/change-set-cs",
            work_branch="factory/cs/diagnose",
        )
        producer.produce.assert_called_once()
        github.ensure_branch_at_sha.assert_called_once_with("factory/cs/diagnose", SHA)
        store.complete_work_unit.assert_called_once_with(
            run_id="run", output_commit=OUTPUT, changed_files=(PATH,),
        )
        self.assertFalse(github.create_pull_request.called)
        self.assertFalse(github.merge_pull_request.called)

    def test_frozen_platform_commit_drift_blocks_before_branch_and_model(self):
        github, store, producer, impact, item = builder_fixture(frozen=NEXT)
        with self.assertRaisesRegex(PermissionError, "frozen Change Set source differs"):
            ChangeSetBuilderWorker(
                github=github, store=store, producer=producer,
                impact_engine=impact, provenance=MagicMock(),
            ).execute(item)
        producer.produce.assert_not_called()
        github.ensure_branch_at_sha.assert_not_called()
        github.commit_files.assert_not_called()
        store.bind_source.assert_not_called()
        store.block_work_unit.assert_called_once()

    def test_platform_cannot_inherit_imported_preview_target(self):
        github, store, producer, impact, item = builder_fixture(
            target={"mode": "open_pr_candidate", "branch": "preview/unrelated"}
        )
        with self.assertRaisesRegex(PermissionError, "platform cannot use"):
            ChangeSetBuilderWorker(
                github=github, store=store, producer=producer,
                impact_engine=impact, provenance=MagicMock(),
            ).execute(item)
        github.get_branch_sha.assert_not_called()
        producer.produce.assert_not_called()

    def test_unknown_project_kind_still_fails_closed(self):
        github, store, producer, impact, item = builder_fixture(kind="platform-like")
        with self.assertRaisesRegex(PermissionError, "unrecognized project kind"):
            ChangeSetBuilderWorker(
                github=github, store=store, producer=producer,
                impact_engine=impact, provenance=MagicMock(),
            ).execute(item)
        github.commit_files.assert_not_called()
        producer.produce.assert_not_called()

    def test_invalid_platform_main_sha_blocks_source_binding(self):
        github, store, producer, impact, item = builder_fixture(main="floating-main")
        with self.assertRaisesRegex(PermissionError, "verified exact SHA"):
            ChangeSetBuilderWorker(
                github=github, store=store, producer=producer,
                impact_engine=impact, provenance=MagicMock(),
            ).execute(item)
        store.bind_source.assert_not_called()
        producer.produce.assert_not_called()


class PlatformIntegrationClaimTests(unittest.TestCase):
    def make_store(self, kind="platform", target=None):
        store = SupabaseChangeSetStore(
            url="https://example.supabase.co", service_role_key="fake"
        )
        store._get = MagicMock(return_value=[{
            "project_kind": kind, "repository": REPO,
            "manifest": {"delivery_target": target} if target else {},
        }])
        payload = {
            "change_set_id": "11111111-1111-4111-8111-111111111111",
            "project_id": "22222222-2222-4222-8222-222222222222",
            "execution_generation": 2,
            "lease_owner": "worker",
            "project_key": "platform-demo",
            "repository": REPO,
            "source_commit": SHA,
            "candidate_commit": SHA,
            "integration_branch": "factory/change-set-cs",
            "current_wave": 1,
            "work_units": [{
                "plan_task_key": "DIAGNOSE", "base_commit": SHA,
                "output_commit": OUTPUT,
                "changed_files": [PATH],
            }],
        }
        store._rpc = MagicMock(return_value=payload)
        return store

    def test_only_explicit_platform_claim_can_pass_with_same_repository(self):
        store = self.make_store()
        claim = store.claim_integration("worker")
        self.assertEqual(claim.project_kind, "platform")
        self.assertEqual(claim.repository, REPO)
        self.assertEqual(claim.source_commit, SHA)
        self.assertIsNone(claim.delivery_target)
        store._rpc.assert_called_once()

    def test_invalid_kind_or_target_fails_closed(self):
        for kind, target in (
            ("platform-ish", None),
            ("platform", {"branch": "preview/unrelated"}),
        ):
            store = self.make_store(kind=kind, target=target)
            with self.subTest(kind=kind), self.assertRaises(PermissionError):
                store.claim_integration("worker")

    def test_cross_repo_project_record_blocks_claim(self):
        store = self.make_store()
        store._get.return_value = [{
            "project_kind": "platform", "repository": "owner/unrelated", "manifest": {},
        }]
        with self.assertRaisesRegex(PermissionError, "identity unavailable or mismatched"):
            store.claim_integration("worker")


class PlatformIntegratorTests(unittest.TestCase):
    def make_item(self):
        return ChangeSetIntegrationItem(
            change_set_id="cs", project_key="platform-demo", repository=REPO,
            source_commit=SHA, candidate_commit=SHA,
            integration_branch="factory/change-set-cs", current_wave=1,
            work_units=({
                "plan_task_key": "DIAGNOSE", "base_commit": SHA,
                "output_commit": OUTPUT, "changed_files": [PATH],
            },), project_kind="platform",
        )

    def fake_github(self, *, main=SHA, pr_base="main"):
        gh = MagicMock()
        gh.repository = REPO
        gh.get_branch_sha.side_effect = lambda branch: (
            main if branch == "main" else NEXT
        )
        gh.get_file_text.return_value = "def audit(): return True\n"
        gh.commit_files.return_value = NEXT
        gh.find_open_issue_containing.return_value = None
        gh.create_issue.return_value = SimpleNamespace(
            number=77, html_url="https://github.com/owner/platform-repo/issues/77"
        )
        gh.find_open_pull_request_containing.return_value = None
        gh.create_pull_request.return_value = SimpleNamespace(
            number=88, head_sha=NEXT, base_ref=pr_base
        )
        return gh

    def fake_store(self):
        store = MagicMock()
        store.complete_integration.return_value = {
            "status": "review_ready",
            "change_set_id": "cs",
            "candidate_commit": NEXT,
            "current_wave": 1,
            "repair_jobs_integrated": 0,
        }
        store.prepare_release.return_value = {
            "change_set_id": "cs", "status": "ci_pending", "release_run_id": "run"
        }
        return store

    def test_platform_creates_nonmerged_pr_to_protected_main(self):
        gh = self.fake_github()
        store = self.fake_store()
        result = ChangeSetIntegrator(github=gh, store=store).integrate(self.make_item())
        self.assertEqual(result.status, "ci_pending")
        self.assertEqual(result.pull_request.number, 88)
        gh.create_pull_request.assert_called_once()
        self.assertEqual(gh.create_pull_request.call_args.kwargs["base"], "main")
        gh.ensure_branch_at_sha.assert_called_once_with("factory/change-set-cs", SHA)
        gh.merge_pull_request.assert_not_called()
        store.prepare_release.assert_called_once()

    def test_platform_main_drift_blocks_before_all_writes(self):
        gh = self.fake_github(main=NEXT)
        store = self.fake_store()
        with self.assertRaisesRegex(PermissionError, "main advanced"):
            ChangeSetIntegrator(github=gh, store=store).integrate(self.make_item())
        gh.get_file_text.assert_not_called()
        gh.ensure_branch_at_sha.assert_not_called()
        gh.commit_files.assert_not_called()
        gh.create_pull_request.assert_not_called()
        store.complete_integration.assert_not_called()

    def test_platform_rejects_cross_repo_or_preview_target(self):
        for item, github in (
            (replace(self.make_item(), delivery_target={"branch": "preview/x"}), self.fake_github()),
            (self.make_item(), self.fake_github()),
        ):
            if item.delivery_target is None:
                github.repository = "owner/unrelated"
            with self.assertRaises(PermissionError):
                ChangeSetIntegrator(github=github, store=self.fake_store()).integrate(item)
            github.commit_files.assert_not_called()

    def test_pr_with_wrong_base_is_not_persisted_as_released(self):
        gh = self.fake_github(pr_base="preview/unauthorized")
        store = self.fake_store()
        with self.assertRaisesRegex(PermissionError, "PR base"):
            ChangeSetIntegrator(github=gh, store=store).integrate(self.make_item())
        store.prepare_release.assert_not_called()


class PlatformKindRecoveryMigrationTests(unittest.TestCase):
    def test_no_unscoped_retry_or_automatic_data_mutations(self):
        path = ROOT / "supabase/migrations/20261020032500_retry_blocked_platform_kind.sql"
        sql = path.read_text()
        for required in (
            "security invoker",
            "p_expected_run_id uuid",
            "p_expected_generation bigint",
            "project_kind is distinct from 'platform'",
            "v_set.status<>'blocked'",
            "implementation_preflight_error",
            "PermissionError: unrecognized project kind",
            "v_set.source_commit is not null",
            "v_set.candidate_commit is not null",
            "v_unit.output_commit is not null",
            "v_run.lease_owner is not null",
            "v_control.generation is distinct from p_expected_generation",
            "v_task.parent_task_id is distinct from v_set.root_task_id",
            "v_unit.run_id is distinct from p_expected_run_id",
            "change_set.platform_kind_requeued",
            "revoke all on function public.factory_retry_blocked_platform_kind",
            "from public,anon,authenticated",
            "to service_role",
        ):
            with self.subTest(marker=required):
                self.assertIn(required,sql)
        self.assertNotIn("security definer",sql.lower())
        self.assertNotIn("merge_pull_request",sql)
        self.assertNotIn("openai",sql.lower())
        self.assertNotIn("factory_claim_next_run",sql)
        self.assertNotIn("factory_retry_failed_run",sql)
        self.assertNotIn("do $repair$",sql.lower())
        self.assertIn("v_unit.changed_files is distinct from '[]'::jsonb",sql)


if __name__ == "__main__":
    unittest.main()
