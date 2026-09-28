import json
import unittest

from ai_product_factory.supabase_store import SupabaseControlPlaneStore


class FakeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        payload = json.loads(body.decode()) if body else None
        self.calls.append((method, url, headers, payload))
        if "factory_projects?" in url:
            return 200, [{
                "id": "p1", "project_key": "demo", "name": "Demo",
                "repository": "owner/demo", "project_kind": "application",
                "lifecycle_stage": "discovery",
            }]
        if url.endswith("/factory_projects"):
            return 201, [{
                "id": "p1", "project_key": payload["project_key"], "name": payload["name"],
                "repository": payload["repository"], "project_kind": payload["project_kind"],
                "lifecycle_stage": "discovery",
            }]
        if url.endswith("/factory_tasks"):
            return 201, [{
                "id": "t1", "project_id": payload["project_id"], "title": payload["title"],
                "description": payload["description"], "status": "queued",
                "complexity": payload["complexity"],
                "acceptance_criteria": payload["acceptance_criteria"],
            }]
        if "factory_tasks?" in url:
            return 200, [{
                "id": "t1", "project_id": "p1", "title": "Task", "description": "",
                "status": payload["status"], "complexity": "low", "acceptance_criteria": [],
            }]
        if url.endswith("/factory_runs"):
            return 201, [{
                "id": "r1", "task_id": payload["task_id"], "status": "created",
                "execution_route": payload["execution_route"],
                "source_commit": payload["source_commit"],
                "candidate_commit": None,
                "branch_name": payload["branch_name"],
            }]
        if "factory_runs?" in url:
            return 200, [{
                "id": "r1", "task_id": "t1", "status": payload["status"],
                "execution_route": "direct", "source_commit": "abc",
                "candidate_commit": payload.get("candidate_commit"), "branch_name": "feat/x",
            }]
        if url.endswith("/factory_decisions"):
            return 201, [{"id": "d1", **payload}]
        if url.endswith("/factory_tool_usage"):
            return 201, [{"id": 1, **payload}]
        if "factory_tool_usage?" in url:
            return 200, [{
                "id": 1, "run_id": "r1", "tool_family": "openai",
                "operation": payload.get("operation"), "usage_units": payload.get("usage_units"),
                "estimated_cost": payload.get("estimated_cost"), "metadata": payload.get("metadata") or {},
            }]
        if url.endswith("/factory_codex_usage"):
            return 201, [{"id": 1, **payload}]
        return 500, {"message": "unexpected"}


class SupabaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.store = SupabaseControlPlaneStore(
            url="https://example.supabase.co",
            secret_key="sb_secret_test",
            transport=self.transport,
        )

    def test_secret_is_only_sent_in_apikey_header(self):
        self.store.get_project_by_key("demo")
        _, _, headers, _ = self.transport.calls[-1]
        self.assertEqual(headers["apikey"], "sb_secret_test")
        self.assertNotIn("Authorization", headers)

    def test_create_project_and_get_project(self):
        created = self.store.create_project(
            project_key="demo", name="Demo", repository="owner/demo", project_kind="application"
        )
        found = self.store.get_project_by_key("demo")
        self.assertEqual(created.project_key, "demo")
        self.assertEqual(found.id, "p1")

    def test_task_and_run_lifecycle(self):
        task = self.store.create_task(
            project_id="p1", title="Task", acceptance_criteria=("green",)
        )
        task = self.store.update_task_status(task.id, "in_progress")
        run = self.store.create_run(
            task_id=task.id, execution_route="direct", source_commit="abc", branch_name="feat/x"
        )
        run = self.store.update_run_status(run.id, "validated", candidate_commit="def")
        self.assertEqual(task.status, "in_progress")
        self.assertEqual(run.status, "validated")
        self.assertEqual(run.candidate_commit, "def")

    def test_records_decision_and_usage(self):
        decision = self.store.record_decision(
            project_id="p1", task_id="t1", decision_type="route",
            decision={"route": "direct"}, decided_by="factory"
        )
        tool = self.store.record_tool_usage(
            run_id="r1", tool_family="github", operation="create_pr"
        )
        codex = self.store.record_codex_usage(
            run_id="r1", policy_level=0, invocation_count=0,
            reasons=("direct sufficient",)
        )
        self.assertEqual(decision.decision["route"], "direct")
        self.assertEqual(tool.tool_family, "github")
        self.assertEqual(codex.invocation_count, 0)

    def test_update_tool_usage_can_clear_cost_to_unknown(self):
        row = self.store.update_tool_usage(
            1,
            operation="model_call_cost_unknown",
            usage_units=0,
            estimated_cost=None,
            metadata={"status": "cost_unknown"},
        )
        method, _, _, payload = self.transport.calls[-1]
        self.assertEqual(method, "PATCH")
        self.assertIn("estimated_cost", payload)
        self.assertIsNone(payload["estimated_cost"])
        self.assertIsNone(row.estimated_cost)

    def test_missing_credentials_fail_fast(self):
        with self.assertRaises(ValueError):
            SupabaseControlPlaneStore(url="", secret_key="x", transport=self.transport)
        with self.assertRaises(ValueError):
            SupabaseControlPlaneStore(url="https://x", secret_key="", transport=self.transport)


if __name__ == "__main__":
    unittest.main()
