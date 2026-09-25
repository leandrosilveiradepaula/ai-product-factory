import unittest

from ai_product_factory.control_plane import MemoryControlPlaneStore


class MemoryControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryControlPlaneStore()
        self.project = self.store.create_project(
            project_key="demo",
            name="Demo",
            repository="owner/demo",
            project_kind="application",
        )

    def test_records_project_task_run_and_decision(self):
        task = self.store.create_task(
            project_id=self.project.id,
            title="Implementar feature",
            acceptance_criteria=("teste verde",),
        )
        run = self.store.create_run(task_id=task.id, execution_route="direct", branch_name="feat/demo")
        decision = self.store.record_decision(
            project_id=self.project.id,
            task_id=task.id,
            decision_type="execution_route",
            decision={"route": "direct"},
            decided_by="factory",
        )

        self.assertEqual(self.store.get_project_by_key("demo"), self.project)
        self.assertEqual(self.store.tasks[task.id].acceptance_criteria, ("teste verde",))
        self.assertEqual(self.store.runs[run.id].execution_route, "direct")
        self.assertEqual(decision.decision["route"], "direct")

    def test_updates_task_and_run_status(self):
        task = self.store.create_task(project_id=self.project.id, title="Tarefa")
        run = self.store.create_run(task_id=task.id)
        self.assertEqual(self.store.update_task_status(task.id, "in_progress").status, "in_progress")
        updated = self.store.update_run_status(run.id, "validated", candidate_commit="abc123")
        self.assertEqual(updated.status, "validated")
        self.assertEqual(updated.candidate_commit, "abc123")

    def test_records_tool_and_codex_usage(self):
        task = self.store.create_task(project_id=self.project.id, title="Tarefa")
        run = self.store.create_run(task_id=task.id)
        tool = self.store.record_tool_usage(run_id=run.id, tool_family="github", operation="create_pr")
        codex = self.store.record_codex_usage(
            run_id=run.id,
            policy_level=0,
            invocation_count=0,
            reasons=("execucao direta suficiente",),
        )
        self.assertEqual(tool.tool_family, "github")
        self.assertEqual(codex.invocation_count, 0)

    def test_duplicate_project_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create_project(
                project_key="demo",
                name="Duplicado",
                repository="owner/other",
                project_kind="application",
            )

    def test_cross_project_decision_is_rejected(self):
        other = self.store.create_project(
            project_key="other",
            name="Other",
            repository="owner/other",
            project_kind="application",
        )
        task = self.store.create_task(project_id=self.project.id, title="Tarefa")
        with self.assertRaises(ValueError):
            self.store.record_decision(
                project_id=other.id,
                task_id=task.id,
                decision_type="invalid",
                decision={},
                decided_by="factory",
            )

    def test_invalid_codex_usage_is_rejected(self):
        task = self.store.create_task(project_id=self.project.id, title="Tarefa")
        run = self.store.create_run(task_id=task.id)
        with self.assertRaises(ValueError):
            self.store.record_codex_usage(run_id=run.id, policy_level=5, invocation_count=1)
        with self.assertRaises(ValueError):
            self.store.record_codex_usage(run_id=run.id, policy_level=1, invocation_count=-1)


if __name__ == "__main__":
    unittest.main()
