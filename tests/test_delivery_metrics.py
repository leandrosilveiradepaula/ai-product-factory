import unittest
from decimal import Decimal

from ai_product_factory.delivery_metrics import derive_delivery_metrics


def base_kwargs():
    return {
        "source_run": {
            "id": "r-root",
            "execution_route": "direct",
            "created_at": "2026-09-30T03:00:00+00:00",
            "started_at": "2026-09-30T03:01:00+00:00",
            "finished_at": "2026-09-30T03:03:00+00:00",
        },
        "project_key": "demo",
        "family_runs": [
            {
                "id": "r-root",
                "created_at": "2026-09-30T03:00:00+00:00",
                "started_at": "2026-09-30T03:01:00+00:00",
                "finished_at": "2026-09-30T03:03:00+00:00",
            },
            {
                "id": "r-builder",
                "created_at": "2026-09-30T03:04:00+00:00",
                "started_at": "2026-09-30T03:05:00+00:00",
                "finished_at": "2026-09-30T03:08:00+00:00",
            },
        ],
        "team_plan": {
            "plan": {
                "profiles_selected": 3,
                "selected_agents": [{"agent_key": "development"}, {"agent_key": "qa"}, {"agent_key": "security"}],
            }
        },
        "work_units": [{"agent_key": "development", "run_id": "r-builder"}],
        "specialist_jobs": [{"role": "qa"}, {"role": "security"}],
        "tool_usage": [
            {
                "tool_family": "openai",
                "operation": "implementation",
                "estimated_cost": "0.0123",
                "metadata": {
                    "input_tokens": 100,
                    "output_tokens": 40,
                    "cached_input_tokens": 20,
                },
                "created_at": "2026-09-30T03:05:00+00:00",
            },
            {
                "tool_family": "github",
                "operation": "preview_not_required_awaiting_human_merge",
                "estimated_cost": None,
                "metadata": {},
                "created_at": "2026-09-30T03:10:00+00:00",
            },
        ],
        "codex_usage": [{"invocation_count": 0}],
        "evaluations": [{"eval_type": "quality_gate", "status": "success"}],
        "repair_jobs": [],
        "audit_events": [
            {
                "event_type": "run.stage.recorded",
                "payload": {"stage": "planning", "status": "started"},
                "created_at": "2026-09-30T03:01:00+00:00",
            },
            {
                "event_type": "run.stage.recorded",
                "payload": {"stage": "planning", "status": "completed"},
                "created_at": "2026-09-30T03:02:30+00:00",
            },
        ],
        "release_reports": [
            {
                "status": "released",
                "created_at": "2026-09-30T03:10:00+00:00",
                "updated_at": "2026-09-30T03:12:00+00:00",
            }
        ],
    }


class DeliveryMetricsTests(unittest.TestCase):
    def test_derives_time_agents_cost_tokens_and_first_pass_ci(self):
        metrics = derive_delivery_metrics(**base_kwargs())
        self.assertEqual(metrics.queue_wait_seconds, 60.0)
        self.assertEqual(metrics.stage_seconds, {"planning": 90.0})
        self.assertEqual(metrics.time_to_awaiting_release_seconds, 600.0)
        self.assertEqual(metrics.time_to_release_seconds, 720.0)
        self.assertEqual(metrics.delivery_seconds, 720.0)
        self.assertEqual(metrics.planned_agents, 3)
        self.assertEqual(metrics.builder_agents, ("development",))
        self.assertEqual(metrics.specialist_agents, ("qa", "security"))
        self.assertEqual(metrics.actual_agent_count, 3)
        self.assertEqual(metrics.known_cost_usd, Decimal("0.0123"))
        self.assertEqual(metrics.unknown_paid_cost_events, 0)
        self.assertEqual(metrics.input_tokens, 100)
        self.assertEqual(metrics.output_tokens, 40)
        self.assertEqual(metrics.cached_input_tokens, 20)
        self.assertTrue(metrics.ci_observed)
        self.assertTrue(metrics.first_pass_ci)
        self.assertEqual(metrics.total_repairs, 0)

    def test_unknown_paid_cost_remains_explicit_and_repairs_break_first_pass(self):
        kwargs = base_kwargs()
        kwargs["tool_usage"] = list(kwargs["tool_usage"]) + [
            {
                "tool_family": "openai",
                "operation": "second_call",
                "estimated_cost": None,
                "metadata": {"input_tokens": 5, "output_tokens": 2},
                "created_at": "2026-09-30T03:06:00+00:00",
            },
            {
                "tool_family": "ci_repair",
                "operation": "repair_attempt",
                "estimated_cost": None,
                "metadata": {"attempt": 1},
                "created_at": "2026-09-30T03:09:00+00:00",
            },
        ]
        kwargs["repair_jobs"] = [{"id": "rep-1", "cycle": 1}]
        metrics = derive_delivery_metrics(**kwargs)
        self.assertEqual(metrics.unknown_paid_cost_events, 1)
        self.assertFalse(metrics.first_pass_ci)
        self.assertEqual(metrics.ci_repairs, 1)
        self.assertEqual(metrics.specialist_repairs, 1)
        self.assertEqual(metrics.total_repairs, 2)

    def test_first_pass_ci_is_unknown_until_ci_is_observed(self):
        kwargs = base_kwargs()
        kwargs["evaluations"] = []
        kwargs["audit_events"] = [
            x for x in kwargs["audit_events"] if x["event_type"] == "run.stage.recorded"
        ]
        metrics = derive_delivery_metrics(**kwargs)
        self.assertFalse(metrics.ci_observed)
        self.assertIsNone(metrics.first_pass_ci)

    def test_planned_agents_falls_back_to_selected_agents(self):
        kwargs = base_kwargs()
        kwargs["team_plan"] = {"plan": {"selected_agents": [{"agent_key": "dev"}, {"agent_key": "qa"}]}}
        metrics = derive_delivery_metrics(**kwargs)
        self.assertEqual(metrics.planned_agents, 2)


if __name__ == "__main__":
    unittest.main()
