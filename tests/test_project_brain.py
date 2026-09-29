import unittest

from ai_product_factory.project_brain import build_project_brain_graph


class ProjectBrainTests(unittest.TestCase):
    def test_planning_graph_contains_tasks_scopes_capabilities_and_dependencies(self):
        graph=build_project_brain_graph(
            project_key="demo",
            engineering_plan={"tasks":[
                {"task_key":"api","title":"API","required_capabilities":["implementation"],"scope_keys":["src/api"],"depends_on":[]},
                {"task_key":"ui","title":"UI","required_capabilities":["ui"],"scope_keys":["apps/web"],"depends_on":["api"]},
            ]},
            context={},
        )
        nodes={x["key"]:x for x in graph.nodes}
        edges={x["key"]:x for x in graph.edges}
        self.assertIn("project:demo",nodes)
        self.assertIn("task:api",nodes)
        self.assertIn("scope:src/api",nodes)
        self.assertIn("capability:implementation",nodes)
        self.assertEqual(edges["ui-depends-api"]["relation"],"depends_on")
        self.assertEqual(nodes["task:api"]["source_refs"],["planning"])

    def test_existing_project_sources_and_evidence_are_provenanced(self):
        graph=build_project_brain_graph(
            project_key="crm",
            engineering_plan={"tasks":[]},
            context={"state_snapshot":{
                "source_status":{"github_repository":"available"},
                "evidence":[{"source":"github","head_sha":"abc"}],
            }},
        )
        node_types={x["type"] for x in graph.nodes}
        self.assertIn("source",node_types)
        self.assertIn("evidence",node_types)
        evidence=next(x for x in graph.nodes if x["type"]=="evidence")
        self.assertEqual(evidence["source_refs"],["state_snapshot"])

    def test_graph_is_stable_for_same_input(self):
        kwargs={"project_key":"demo","engineering_plan":{"tasks":[
            {"task_key":"a","title":"A","required_capabilities":["implementation"],"scope_keys":["src/a"],"depends_on":[]}
        ]},"context":{}}
        a=build_project_brain_graph(**kwargs)
        b=build_project_brain_graph(**kwargs)
        self.assertEqual(a,b)


if __name__=="__main__":
    unittest.main()
