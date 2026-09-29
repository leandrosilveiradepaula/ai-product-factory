import unittest

from ai_product_factory.impact_engine import analyze_project_brain_impact


class ImpactEngineTests(unittest.TestCase):
    def test_task_seed_traverses_scope_and_downstream_dependency(self):
        nodes=[
            {"id":"1","snapshot_id":"s","node_key":"task:api","node_type":"task","name":"API"},
            {"id":"2","snapshot_id":"s","node_key":"scope:src/api","node_type":"scope","name":"src/api"},
            {"id":"3","snapshot_id":"s","node_key":"task:ui","node_type":"task","name":"UI"},
            {"id":"4","snapshot_id":"s","node_key":"capability:implementation","node_type":"capability","name":"implementation"},
        ]
        edges=[
            {"from_node_id":"1","to_node_id":"2","relation":"may_modify"},
            {"from_node_id":"1","to_node_id":"4","relation":"requires"},
            {"from_node_id":"3","to_node_id":"1","relation":"depends_on"},
        ]
        out=analyze_project_brain_impact(nodes=nodes,edges=edges,task_key="api")
        keys={row["node_key"] for row in out.impacted_nodes}
        self.assertEqual(out.confidence,"high")
        self.assertIn("scope:src/api",keys)
        self.assertIn("task:ui",keys)
        self.assertIn("capability:implementation",keys)
        self.assertEqual(out.unknowns,())

    def test_missing_task_is_unknown_not_invented(self):
        out=analyze_project_brain_impact(nodes=[],edges=[],task_key="missing")
        self.assertEqual(out.confidence,"unknown")
        self.assertEqual(out.impacted_nodes,())
        self.assertIn("task node not found",out.unknowns[0])


if __name__=="__main__":
    unittest.main()
