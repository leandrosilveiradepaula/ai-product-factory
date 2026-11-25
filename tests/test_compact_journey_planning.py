import copy
import json
import unittest
from decimal import Decimal

from ai_product_factory.agent_scheduler import AgentProfile
from ai_product_factory.compact_journey_planning import compact_context, planning_schema
from ai_product_factory.model_executor import ModelExecutor, ModelResult, ModelRole
from ai_product_factory.private_model_metering import PrivatePricing, MeteredPrivateProvider
from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.product_stage_output_contract import (
    ProductStageOutputTruncated, decode_product_stage_object,
)
from ai_product_factory.runtime_worker import RuntimeWorker, WorkItem, WorkStatus


SHA = "a" * 40
PRIOR = {
    "discovery": {"problem": "Existing editorial flow incomplete", "_evidence": {"provider_ref": "d"}},
    "specification": {"scope": "Complete authenticated editorial delivery",
                      "requirements": ["preserve approved records"], "_evidence": {"provider_ref": "s"}},
}
PLAN = {"tasks": [{"task_key": "editorial-flow", "title": "Complete editorial flow",
                   "description": "Integrate editorial actions into the authenticated application.",
                   "required_capabilities": ["implementation"], "preferred_agent_role": "development",
                   "scope_keys": ["app/editorial.js", "app/editorial.test.js"],
                   "context_paths": ["app/editorial.js"], "depends_on": [],
                   "acceptance_criteria": ["Existing editor regression tests pass."]}],
        "specialist_reviews": ["security", "qa", "operations"], "decisions_needed": []}


def work():
    return WorkItem("run", "task", "project", "dark-channel-studio", ("planning",), {
        "manifest": {"onboarding_mode": "greenfield", "source": "factory-console",
                     "human_decisions": [{"decision_key": "editor", "answer": "approved"}],
                     "engineering_plan": {"architecture": "old narrative " * 4000,
                                          "tasks": [{"task_key": "old", "risk": {"production_change": True}}],
                                          "decisions_needed": [{"decision_key": "old"}]}},
        "journey_binding_v2": {"journey_id": "journey", "request_id": "request", "source_commit": SHA},
        "journey_request": {"text": "Complete authenticated editorial delivery"},
        "_verified_resume_prior_stages": copy.deepcopy(PRIOR),
        "_verified_resume_origin": {"generation": 1, "prior_kind": "greenfield",
                                    "request_id": "request", "snapshot_id": SHA},
        "current_state_facts": {"live_candidate": {
            "observed_from": "journey_delivery_binding_v2", "journey_id": "journey", "sha": SHA,
            "source_evidence": {"assessed_commit": SHA, "status": "bounded_source_inspected",
                                "inspected_files": [{"path": "app/editorial.js", "content": "export function edit() {}"}]}}}
    }, execution_generation=1, worker_id="worker", journey_id="journey")


class Provider:
    def __init__(self, results):
        self.results = iter(results)
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return next(self.results)


class Ledger:
    def __init__(self):
        self.reservations = []
        self.settlements = []

    def record_tool_usage(self, **kwargs):
        self.reservations.append(kwargs)
        return type("Receipt", (), {"id": len(self.reservations)})()

    def update_tool_usage(self, receipt, **kwargs):
        self.settlements.append((receipt, kwargs))


class Queue:
    def __init__(self, *, revoke=False):
        self.item = work()
        self.events = []
        self.checks = 0
        self.revoke = revoke

    def claim_next(self, worker_id):
        return self.item

    def assert_execution_epoch(self, item):
        self.checks += 1
        if self.revoke and self.checks >= 2:
            raise PermissionError("project execution epoch revoked")

    def record_stage_event(self, item, stage, status):
        self.events.append((stage, status))

    def record_stage(self, item, ev):
        self.events.append((ev.stage, ev.status))

    def complete(self, item):
        self.events.append(("run", "completed"))

    def fail(self, item, error):
        self.events.append(("run", "failed"))


def result(text, *, cap=False, truncated=False):
    return ModelResult(ModelRole.PRIMARY, text, provider_ref="infodive_ibm_cloud",
                       model="SQL-InfoDive",
                       usage={"input_tokens": 16386, "output_tokens": 4096 if cap else 800},
                       output_limit_reached=cap, output_truncated=truncated)


def handler(provider):
    dev = AgentProfile("dev", "development", ("implementation",),
                       ("github_write", "github_read"), {}, 1, 0.5, True)
    return ProductStageExecutor(ModelExecutor(primary=provider), team_profiles=(dev,))


class CompactPlanningTests(unittest.TestCase):
    def test_exact_checkpoint_and_scope_preserved_with_compact_schema(self):
        item = work()
        original = copy.deepcopy(item.context)
        provider = Provider([result(json.dumps(PLAN))])
        out = handler(provider).execute(item, "planning")
        self.assertEqual(out["tasks"], PLAN["tasks"])
        req = provider.requests[0]
        data = json.loads(req.context)
        self.assertEqual(data["prior_stages"], PRIOR)
        self.assertEqual(data["intake"]["journey_request"], original["journey_request"])
        self.assertEqual(data["intake"]["current_state_facts"], original["current_state_facts"])
        self.assertEqual(data["intake"]["manifest"]["human_decisions"], original["manifest"]["human_decisions"])
        self.assertEqual(data["intake"]["manifest"]["engineering_plan"]["tasks"],
                         original["manifest"]["engineering_plan"]["tasks"])
        self.assertEqual(data["intake"]["manifest"]["engineering_plan"],
                         original["manifest"]["engineering_plan"])
        self.assertNotIn("_verified_resume_prior_stages", data["intake"])
        self.assertEqual(item.context, original)
        self.assertEqual(req.output_schema, planning_schema())
        self.assertIn("2500 output tokens", req.objective)

    def test_complete_fenced_json_and_invalid_partial_outputs(self):
        self.assertEqual(decode_product_stage_object(result("```json\n{\"tasks\":[]}\n```"), "planning"),
                         {"tasks": []})
        for text in ('prefix {"tasks":[]}', '{"tasks":[]} trailing', '{"x":1,"x":2}',
                     '{"x":NaN}', '{"tasks": [', '```json\n{"x":1}'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "invalid JSON"):
                decode_product_stage_object(result(text), "planning")
        with self.assertRaises(ProductStageOutputTruncated):
            decode_product_stage_object(result('{"tasks": [', cap=True), "planning")
        with self.assertRaises(ProductStageOutputTruncated):
            decode_product_stage_object(result('{"tasks":[]}', truncated=True), "planning")
        self.assertEqual(decode_product_stage_object(result('{"tasks":[]}', cap=True), "planning"), {"tasks":[]})

    def test_only_one_metered_zero_price_retry_and_fresh_epoch(self):
        for scenario in ("success", "again", "paid", "revoked", "unmetered"):
            with self.subTest(scenario=scenario):
                first = result('{"tasks":[', cap=True)
                second = first if scenario == "again" else result(json.dumps(PLAN))
                raw = Provider([first, second])
                ledger = Ledger()
                if scenario == "unmetered":
                    provider = raw
                else:
                    rate = Decimal("0.01") if scenario == "paid" else Decimal(0)
                    provider = MeteredPrivateProvider(raw, PrivatePricing(rate, rate),
                                                       store=ledger, reserve=Decimal("0.5"))
                queue = Queue(revoke=scenario == "revoked")
                response = RuntimeWorker(queue=queue, handler=handler(provider),
                                         worker_id="worker").run_once()
                expected_calls = 2 if scenario in {"success", "again"} else 1
                self.assertEqual(len(raw.requests), expected_calls)
                self.assertEqual(response.status, WorkStatus.COMPLETED if scenario == "success" else WorkStatus.FAILED)
                if expected_calls == 2:
                    self.assertIn("1600 output tokens", raw.requests[1].objective)
                    self.assertEqual(raw.requests[0].context, raw.requests[1].context)
                    self.assertGreaterEqual(queue.checks, 2)
                    self.assertEqual(len(ledger.settlements), 2)
                    self.assertTrue(all(x[1]["estimated_cost"] == 0 for x in ledger.settlements))
                self.assertEqual(("run", "completed") in queue.events, scenario == "success")

    def test_no_empty_acceptance_or_unscoped_task(self):
        bad = copy.deepcopy(PLAN)
        bad["tasks"][0]["acceptance_criteria"] = []
        provider = Provider([result(json.dumps(bad))])
        with self.assertRaisesRegex(ValueError, "verifiable acceptance"):
            handler(provider).execute(work(), "planning")


if __name__ == "__main__":
    unittest.main()
