import unittest

from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.models import Complexity, ExecutionRoute, RiskProfile, TaskProfile
from ai_product_factory.runtime import FactoryRuntime


class FactoryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryControlPlaneStore()
        self.project = self.store.create_project(
            project_key="demo",
            name="Demo",
            repository="owner/demo",
            project_kind="application",
        )
        self.runtime = FactoryRuntime(self.store)

    def test_start_task_persists_direct_route_and_zero_codex_invocations(self):
        started = self.runtime.start_task(
            project_key="demo",
            title="Small change",
            task_profile=TaskProfile(complexity=Complexity.LOW, estimated_files=2),
            source_commit="abc",
            branch_name="feat/small",
        )
        self.assertEqual(started.decision.route, ExecutionRoute.DIRECT)
        self.assertEqual(self.store.tasks[started.task.id].status, "in_progress")
        self.assertEqual(self.store.runs[started.run.id].status, "in_progress")
        self.assertEqual(self.store.codex_usage[-1].invocation_count, 0)
        self.assertEqual(self.store.decisions[-1].decision["route"], "direct")

    def test_complex_task_routes_to_codex_without_forcing_human_gate(self):
        started = self.runtime.start_task(
            project_key="demo",
            title="Deep refactor",
            task_profile=TaskProfile(
                complexity=Complexity.HIGH,
                estimated_files=30,
                deep_debug=True,
                large_refactor=True,
            ),
        )
        self.assertEqual(started.decision.route, ExecutionRoute.CODEX)
        self.assertFalse(started.decision.human_gate_required)
        self.assertTrue(self.store.decisions[-1].decision["codex_used"])

    def test_simple_production_task_records_gate_independently(self):
        started = self.runtime.start_task(
            project_key="demo",
            title="Production config",
            task_profile=TaskProfile(complexity=Complexity.LOW),
            risk=RiskProfile(production_change=True),
        )
        self.assertEqual(started.decision.route, ExecutionRoute.DIRECT)
        self.assertTrue(started.decision.human_gate_required)
        self.assertTrue(self.store.decisions[-1].decision["human_gate_required"])

    def test_finish_task_updates_run_and_task(self):
        started = self.runtime.start_task(
            project_key="demo",
            title="Feature",
            task_profile=TaskProfile(),
        )
        self.runtime.record_tool(started.run.id, tool_family="github", operation="create_pr")
        self.runtime.finish_task(started, status="merged", candidate_commit="def")
        self.assertEqual(self.store.runs[started.run.id].candidate_commit, "def")
        self.assertEqual(self.store.runs[started.run.id].status, "merged")
        self.assertEqual(self.store.tasks[started.task.id].status, "completed")
        self.assertEqual(self.store.tool_usage[-1].operation, "create_pr")

    def test_unknown_project_is_rejected(self):
        with self.assertRaises(KeyError):
            self.runtime.start_task(
                project_key="missing",
                title="x",
                task_profile=TaskProfile(),
            )


if __name__ == "__main__":
    unittest.main()
