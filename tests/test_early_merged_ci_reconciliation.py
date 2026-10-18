"""Fail-closed tests for a GitHub PR merged before Factory quality/Preview gates."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_product_factory.runtime_cli import run_ci_once
from ai_product_factory.supabase_delivery_store import SupabaseDeliveryStore

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "supabase/migrations/20261016120000_block_early_merged_ci_candidates.sql").read_text()


def candidate(*, merged=True, sha="a" * 40, merge_sha="b" * 40):
    return SimpleNamespace(
        number=7, head_sha=sha, merged=merged, state="closed" if merged else "open",
        merge_commit_sha=merge_sha,
    )


class MergedBeforeReadinessTests(unittest.TestCase):
    def run_once(self, pr):
        item = SimpleNamespace(
            run_id="run-1", issue_number=6, repository="owner/private",
            pr_number=7, candidate_commit="a" * 40, branch="factory/candidate",
            human_gate_required=False,
        )
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue") as q, \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github_adapter, \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore") as store:
            q.return_value.next_pending.return_value = item
            github = github_adapter.return_value
            github.get_pull_request.return_value = pr
            store.return_value.block_early_merged_ci_candidate.return_value = {
                "run_id": item.run_id,
                "status": "blocked",
                "merge_sha": "b" * 40,
                "change_set_id": "change-set-1",
                "idempotent": False,
            }
            try:
                result = run_ci_once()
            except Exception as exc:
                result = exc
            return result, item, github, store.return_value

    def test_early_merge_blocks_atomically_without_forged_ci(self):
        result, item, github, store = self.run_once(candidate())
        self.assertEqual(result["status"], "merged_before_readiness_blocked")
        self.assertEqual(result["merge_sha"], "b" * 40)
        self.assertEqual(result["change_set_id"], "change-set-1")
        store.block_early_merged_ci_candidate.assert_called_once_with(
            run_id=item.run_id, repository=item.repository, pr_number=7,
            candidate_commit=item.candidate_commit, merge_sha="b" * 40,
        )
        github.get_ci_state.assert_not_called()
        github.get_issue.assert_not_called()
        github.dispatch_workflow.assert_not_called()
        store.record_evaluation.assert_not_called()
        store.update_run_status.assert_not_called()
        store.finalize_console_human_release.assert_not_called()

    def test_untrusted_changed_head_blocks_without_any_rpc(self):
        result, _, github, store = self.run_once(candidate(sha="c" * 40))
        self.assertEqual(result["status"], "candidate_drift_blocked")
        self.assertEqual(result["recorded_candidate_commit"], "a" * 40)
        self.assertEqual(result["observed_pr_head"], "c" * 40)
        store.block_early_merged_ci_candidate.assert_not_called()
        github.get_ci_state.assert_not_called()

    def test_merge_sha_missing_blocks_without_any_rpc(self):
        result, _, github, store = self.run_once(candidate(merge_sha=None))
        self.assertIsInstance(result, RuntimeError)
        self.assertIn("verifiable merge SHA", str(result))
        store.block_early_merged_ci_candidate.assert_not_called()
        github.get_ci_state.assert_not_called()

    def test_rpc_must_report_blocked_run_and_exact_merge_sha(self):
        with patch.object(SupabaseDeliveryStore, "_rpc", return_value={
            "run_id":"r", "status":"completed", "merge_sha":"m",
        }):
            with patch("ai_product_factory.supabase_delivery_store.resolve_supabase_server_config") as cfg:
                cfg.return_value = SimpleNamespace(url="https://example.invalid", key="x", headers={})
                store = SupabaseDeliveryStore()
                with self.assertRaisesRegex(RuntimeError, "inconsistent evidence"):
                    store.block_early_merged_ci_candidate(
                        run_id="r", repository="owner/private", pr_number=7,
                        candidate_commit="a" * 40, merge_sha="m",
                    )

    def test_postgres_rpc_is_service_role_only_and_security_invoker(self):
        self.assertIn("create or replace function public.factory_block_early_merged_ci_candidate", MIGRATION)
        self.assertIn("security invoker", MIGRATION.lower())
        self.assertNotIn("security definer", MIGRATION.lower())
        self.assertIn("set search_path = ''", MIGRATION)
        self.assertIn("from public, anon, authenticated", MIGRATION)
        self.assertIn("to service_role", MIGRATION)
        self.assertIn("p_candidate_commit !~ '^[0-9a-f]{40}$'", MIGRATION)
        self.assertIn("v_repository is distinct from p_repository", MIGRATION)
        self.assertIn("usage.operation = 'create_pr'", MIGRATION)
        self.assertIn("usage.metadata->>'head_sha' = p_candidate_commit", MIGRATION)
        self.assertIn("and not coalesce((", MIGRATION)

    def test_migration_blocks_run_and_change_set_but_not_release_or_ci(self):
        for text in (
            "v_run.status <> 'ci_pending'",
            "v_set.status <> 'ci_pending'",
            "v_set.project_id <> v_project_id",
            "where release_run_id = p_run_id for update",
            "status = 'blocked'",
            "where id = p_run_id and status = 'ci_pending'",
            "where id = v_set.id and status = 'ci_pending'",
            "release.human_merge_before_readiness_blocked",
            "'quality_gate_passed', false",
            "'preview_verified', false",
            "'release_authorized', false",
            "'needs_reconciliation', true",
            "'external_early_merge'",
            "refusing to override an already released report",
        ):
            with self.subTest(text=text):
                self.assertIn(text, MIGRATION)
        self.assertNotIn("update public.factory_projects", MIGRATION)
        self.assertNotIn("update public.factory_tasks", MIGRATION)
        self.assertNotIn("insert into public.factory_evaluations", MIGRATION)
        self.assertNotIn("factory_mark_released", MIGRATION)

    def test_repeated_observation_is_idempotent_and_does_not_repeat_audit(self):
        self.assertIn("if v_run.status = 'blocked' and", MIGRATION)
        self.assertIn("v_run.metadata->'external_early_merge' = v_evidence", MIGRATION)
        self.assertIn("'idempotent',true", MIGRATION)


if __name__ == "__main__":
    unittest.main()
