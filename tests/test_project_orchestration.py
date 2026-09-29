import unittest

from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.project_orchestration import BootstrapStage, ProjectBootstrapOrchestrator


class ProjectOrchestrationTests(unittest.TestCase):
    def test_enqueue_product_bootstrap_is_durable_and_model_free(self):
        store=MemoryControlPlaneStore()
        project=store.create_project(project_key="demo",name="Demo",repository="",project_kind="greenfield")
        result=ProjectBootstrapOrchestrator(store).enqueue("demo")
        self.assertEqual(result.project,project)
        self.assertEqual(result.task.project_id,project.id)
        self.assertEqual(result.run.task_id,result.task.id)
        self.assertEqual(result.run.execution_route,"direct")
        self.assertEqual(result.stages,(BootstrapStage.DISCOVERY,BootstrapStage.SPECIFICATION,BootstrapStage.PLANNING))
        self.assertEqual(store.tool_usage[-1].estimated_cost,0)
        self.assertEqual(store.tool_usage[-1].metadata["stages"],["discovery","specification","planning"])

    def test_enqueue_rejects_unknown_project(self):
        store=MemoryControlPlaneStore()
        with self.assertRaisesRegex(KeyError,"unknown project"):
            ProjectBootstrapOrchestrator(store).enqueue("missing")


if __name__=="__main__":
    unittest.main()
