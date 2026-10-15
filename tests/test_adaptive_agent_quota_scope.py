"""Regression: Vercel Preview quota must not cancel unrelated Direct code work.

No API calls. External model quotas, paid ledger and profile ceilings still
apply independently. The runtime never infers provider credit from this test.
"""
import unittest
from decimal import Decimal
from types import SimpleNamespace

from ai_product_factory.adaptive_agent_scheduler import (
    SupabaseAdaptiveConcurrencyController,
)


VERCEL_BLOCKED = {
    "provider": "vercel",
    "resource_key": "team",
    "metric_key": "deployments_daily",
    "status": "blocked",
    "observed_at": "2026-10-13T17:38:34Z",
}
DIRECT = {
    "agent_key": "development",
    "run_id": "e0d94242-9236-4288-a415-54d81a9553d7",
}


class AdaptiveAgentQuotaScopeTests(unittest.TestCase):
    def controller(self, snapshots, *, unknown_paid_cost=False):
        instance = SupabaseAdaptiveConcurrencyController.__new__(
            SupabaseAdaptiveConcurrencyController
        )
        recorded = []
        instance.scheduler = SimpleNamespace(
            work_matrix=lambda limit: {"direct": [dict(DIRECT)], "codex": []},
            profiles=lambda: [
                SimpleNamespace(agent_key="development", max_concurrency=3)
            ],
        )
        instance.health = SimpleNamespace(
            read=lambda: SimpleNamespace(
                known_cost=Decimal("3.7210392"),
                unknown_cost_events=int(unknown_paid_cost),
            ),
        )

        def get(path):
            if path.startswith("factory_resource_limit_snapshots?"):
                return snapshots
            if path.startswith("factory_runs?"):
                return []
            if path.startswith("factory_evaluations?"):
                return []
            self.fail("unexpected Control Plane GET: " + path)

        instance._get = get
        instance._rpc = lambda name, payload: recorded.append((name, payload))
        return instance, recorded

    def test_blocked_vercel_deployments_are_not_direct_execution_quota(self):
        instance, calls = self.controller([VERCEL_BLOCKED])
        result = instance.work_matrix(6)
        self.assertEqual(result["direct"], [DIRECT])
        self.assertEqual(result["codex"], [])
        self.assertEqual(result["decisions"][0]["effective_concurrency"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "factory_record_agent_concurrency_decision")
        pressure = calls[0][1]["p_pressure"]
        self.assertEqual(pressure["quota_status"], "unknown")
        self.assertEqual(pressure["preview_deployment_quota_status"], "blocked")
        self.assertEqual(pressure["known_cost"], "3.7210392")
        self.assertTrue(any(
            "unknown provider quota caps concurrency at 1" in reason
            for reason in result["decisions"][0]["reasons"]
        ))

    def test_openai_blocked_quota_still_blocks_direct(self):
        instance, calls = self.controller([
            VERCEL_BLOCKED,
            {
                "provider": "openai",
                "resource_key": "primary",
                "metric_key": "monthly_spend",
                "status": "blocked",
                "observed_at": "2026-10-15T23:52:00Z",
            },
        ])
        result = instance.work_matrix()
        self.assertEqual(result["direct"], [])
        self.assertEqual(result["decisions"][0]["effective_concurrency"], 0)
        self.assertEqual(calls[0][1]["p_pressure"]["quota_status"], "blocked")

    def test_github_blocked_and_unknown_other_provider_still_block(self):
        for provider in ("github_actions", "new_model_provider"):
            with self.subTest(provider=provider):
                instance, _ = self.controller([
                    VERCEL_BLOCKED,
                    {"provider": provider, "resource_key": "global",
                     "metric_key": "rate", "status": "critical"},
                ])
                self.assertEqual(instance.work_matrix()["direct"], [])

    def test_different_vercel_metric_does_not_get_exempted(self):
        instance, _ = self.controller([
            VERCEL_BLOCKED,
            {"provider": "vercel", "resource_key": "model_gateway",
             "metric_key": "model_inference", "status": "blocked"},
        ])
        self.assertEqual(instance.work_matrix()["direct"], [])

    def test_unknown_cost_still_blocks_with_only_vercel_deployment_quota(self):
        instance, _ = self.controller([VERCEL_BLOCKED], unknown_paid_cost=True)
        result = instance.work_matrix()
        self.assertEqual(result["direct"], [])
        self.assertTrue(any(
            "unknown paid cost blocks execution" in text
            for text in result["decisions"][0]["reasons"]
        ))

    def test_other_relevant_quota_attention_conservatively_caps_at_one(self):
        instance, _ = self.controller([
            VERCEL_BLOCKED,
            {"provider": "openai", "resource_key": "primary",
             "metric_key": "requests", "status": "attention"},
        ])
        decision = instance.work_matrix()["decisions"][0]
        self.assertEqual(decision["effective_concurrency"], 1)
        self.assertTrue(any("attention" in reason for reason in decision["reasons"]))

    def test_case_folding_is_exactly_metric_scoped(self):
        rows = [
            {"provider": " VERCEL ", "metric_key": " DEPLOYMENTS_DAILY ",
             "resource_key": "team", "status": "blocked"},
            {"provider": "github", "metric_key": "calls",
             "resource_key": "repo", "status": "normal"},
        ]
        self.assertEqual(
            SupabaseAdaptiveConcurrencyController._execution_quota_status(rows),
            "normal",
        )
        self.assertEqual(
            SupabaseAdaptiveConcurrencyController._preview_deployment_quota_status(rows),
            "blocked",
        )

    def test_no_relevant_snapshot_is_unknown_not_assumed_normal(self):
        self.assertEqual(
            SupabaseAdaptiveConcurrencyController._execution_quota_status(
                [VERCEL_BLOCKED]
            ),
            "unknown",
        )
        self.assertEqual(
            SupabaseAdaptiveConcurrencyController._worst_quota(
                [VERCEL_BLOCKED]
            ),
            "blocked",
        )


if __name__ == "__main__":
    unittest.main()
