"""Executed B2 simulation-denial evidence at real Factory runtime entrypoints.

The test harness replaces network/paid/privileged adapters with FAILING
sentinels. It does not claim a live provider authorization or production E2E.
Any unexpected side effect fails the test. This source is blob-pinned by the
independent post-CI criterion verifier.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_product_factory import runtime_cli as cli


class SimulationRuntimeAdmissionEvidence(unittest.TestCase):
    def test_disabled_primary_and_codex_block_before_any_external_adapter(self):
        with patch.dict(os.environ, {
            "FACTORY_PRIMARY_MODEL_ENABLED": "false",
            "FACTORY_CODEX_ENABLED": "false",
            "CHATGPT_ACCESS_TOKEN": "untrusted-synthetic",
            "OPENAI_API_KEY": "untrusted-synthetic",
        }, clear=True), \
            patch.object(cli, "SupabaseRuntimeQueue",
                         side_effect=AssertionError("product queue contacted")), \
            patch.object(cli, "SupabaseDirectRunQueue",
                         side_effect=AssertionError("direct queue contacted")), \
            patch.object(cli, "SupabaseCodexRunQueue",
                         side_effect=AssertionError("codex queue contacted")), \
            patch.object(cli, "SupabaseAgentScheduler",
                         side_effect=AssertionError("scheduler contacted")), \
            patch.object(cli, "OpenAIResponsesProvider",
                         side_effect=AssertionError("paid model contacted")), \
            patch.object(cli, "GitHubRestAdapter",
                         side_effect=AssertionError("github contacted")):
            for fn in (cli.run_product_once, cli.run_direct_once,
                       cli.run_codex_once):
                with self.subTest(entrypoint=fn.__name__):
                    result = fn("no-paid-worker")
                    self.assertEqual(result["status"], "blocked")
                    self.assertIs(result["claimed"], False)

    def test_dispatch_denies_before_any_run_claim_when_budget_unknown(self):
        with patch.dict(os.environ, {
            "FACTORY_PRIMARY_MODEL_ENABLED": "false",
            "FACTORY_CODEX_ENABLED": "false",
            "FACTORY_CODEX_MANUAL_FALLBACK_ENABLED": "false",
        }, clear=True), \
            patch.object(cli, "SupabaseBacklogDispatch",
                         side_effect=AssertionError("backlog claimed")), \
            patch.object(cli, "SupabaseAgentScheduler",
                         side_effect=AssertionError("agent scheduled")), \
            patch.object(cli, "OpenAIResponsesProvider",
                         side_effect=AssertionError("provider invoked")):
            out = cli.run_dispatch_once("ai-product-factory")
            self.assertEqual(out["status"], "blocked_executor_readiness")
            self.assertIs(out["claimed"], False)
            self.assertEqual(out["routed"], [])

    def test_pinned_preview_candidate_drift_blocks_before_github_or_deployment(self):
        canonical = "11111111-1111-4111-8111-111111111111"
        expected = "a" * 40
        queue = SimpleNamespace(next_pending=lambda **kwargs: SimpleNamespace(
            run_id=canonical, candidate_commit="b" * 40))
        with patch.object(cli, "SupabasePreviewFollowupQueue",
                          return_value=queue), \
             patch.object(cli, "GitHubRestAdapter",
                          side_effect=AssertionError("Github called")), \
             patch.object(cli, "SupabaseDeliveryStore",
                          side_effect=AssertionError("delivery written")), \
             patch.object(cli, "SupabasePreviewFollowupQueue",
                          return_value=queue):
            with self.assertRaisesRegex(RuntimeError, "candidate changed"):
                cli.run_preview_once(expected_run_id=canonical,
                                     expected_candidate_sha=expected)

    def test_release_observer_rejects_sha_drift_before_store_or_human_release(self):
        candidate, observed = "a" * 40, "b" * 40
        item = SimpleNamespace(
            repository="leandrosilveiradepaula/ai-product-factory",
            run_id="synthetic-run", pr_number=22, candidate_commit=candidate)
        queue = SimpleNamespace(next_pending=lambda: item)
        gh = SimpleNamespace(get_pull_request=lambda n: SimpleNamespace(
            head_sha=observed, base_ref="main", merged=True))
        with patch.object(cli, "SupabaseReleaseFollowupQueue",
                          return_value=queue), \
             patch.object(cli, "_assert_project_followup"), \
             patch.object(cli, "GitHubRestAdapter", return_value=gh), \
             patch.object(cli, "SupabaseDeliveryStore",
                          side_effect=AssertionError("durable release written")), \
             patch.object(cli, "SupabaseReleasePolicyStore",
                          side_effect=AssertionError("release marked")), \
             patch.object(cli, "SupabaseProjectReleaseReconciler",
                          side_effect=AssertionError("release reconciled")):
            out = cli.run_release_once()
        self.assertEqual(out["status"], "candidate_drift_blocked")
        self.assertEqual(out["recorded_candidate_commit"], candidate)
        self.assertEqual(out["observed_pr_head"], observed)

    def test_unauthorized_mutation_is_not_executed_by_checkpointed_github(self):
        class Github:
            def __init__(self):
                self.mutations = 0
            def create_pull_request(self, *args, **kwargs):
                self.mutations += 1
        adapter = Github()
        def reject():
            raise PermissionError("unverified_runtime_epoch")
        protected = cli._CheckpointedGitHub(adapter, reject)
        with self.assertRaisesRegex(PermissionError, "unverified_runtime_epoch"):
            protected.create_pull_request("synthetic")
        self.assertEqual(adapter.mutations, 0)

    def test_read_only_simulation_markers_do_not_authorize_production_release(self):
        from pathlib import Path
        from scripts.audit_block1_mock_runtime_reachability import audit
        from scripts.inventory_block1_simulation_paths import inventory
        root = Path(__file__).resolve().parents[1]
        source = inventory(root)
        static = audit(root)
        self.assertGreater(source["source_files"], 0)
        self.assertGreater(source["marker_occurrences_by_line"], 0)
        self.assertEqual(static["unclassified_runtime_markers"], [])
        self.assertEqual(static["entrypoint"],
                         "src/ai_product_factory/runtime_cli.py")
        self.assertFalse(static["simulation_can_authorize_release"])
        self.assertEqual(static["paid_calls"], 0)
        self.assertEqual(source["writes_to_production"], 0)


if __name__ == "__main__":
    unittest.main()
