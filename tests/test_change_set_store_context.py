import unittest

from ai_product_factory.change_set_store import SupabaseChangeSetStore


class ChangeSetStoreContextTests(unittest.TestCase):
    def test_context_source_enriches_durable_human_decisions_from_project_manifest(self):
        store=SupabaseChangeSetStore(url="https://example.supabase.co",service_role_key="secret")
        store._rpc=lambda name,payload:{
            "project_key":"crm-infodive",
            "repository":"owner/repo",
            "work_unit_id":"wu-1",
            "task":{"title":"debug-route-remediation"},
            "assignment":{"scope_keys":["debug_application"],"required_capabilities":["implementation"]},
        }
        seen=[]
        def get(path):
            seen.append(path)
            if path.startswith("factory_projects?"):
                return [{"manifest":{"human_decisions":[{"gate_id":"g1","response":"Authorize /debug only"}]}}]
            if path.startswith("factory_change_set_work_units?"):
                return [{"task_id":"task-1"}]
            if path.startswith("factory_tasks?"):
                return [{"scope_keys":["src/app/debug/page.tsx"],"required_capabilities":["implementation","debug"],"agent_role":"development"}]
            raise AssertionError(path)
        store._get=get
        source=store.context_source("run-1")
        self.assertEqual(source["human_decisions"],[{"gate_id":"g1","response":"Authorize /debug only"}])
        self.assertEqual(source["assignment"]["scope_keys"],["src/app/debug/page.tsx"])
        self.assertEqual(source["assignment"]["required_capabilities"],["implementation","debug"])
        self.assertEqual(source["assignment"]["agent_role"],"development")
        self.assertTrue(any("project_key=eq.crm-infodive" in path for path in seen))

    def test_context_source_prefers_materialized_task_scope_over_stale_team_plan_scope(self):
        store=SupabaseChangeSetStore(url="https://example.supabase.co",service_role_key="secret")
        store._rpc=lambda name,payload:{
            "project_key":"factory",
            "work_unit_id":"wu-1",
            "assignment":{"scope_keys":[".github","apps","packages"],"required_capabilities":["implementation","backend","supabase"]},
        }
        def get(path):
            if path.startswith("factory_projects?"):
                return [{"manifest":{}}]
            if path.startswith("factory_change_set_work_units?"):
                return [{"task_id":"task-1"}]
            if path.startswith("factory_tasks?"):
                return [{"scope_keys":["src/ai_product_factory/schedule_probe.py"],"required_capabilities":["implementation","integration"],"agent_role":"development"}]
            raise AssertionError(path)
        store._get=get
        source=store.context_source("run-1")
        self.assertEqual(source["assignment"]["scope_keys"],["src/ai_product_factory/schedule_probe.py"])
        self.assertEqual(source["assignment"]["required_capabilities"],["implementation","integration"])

    def test_context_source_defaults_to_empty_durable_decisions(self):
        store=SupabaseChangeSetStore(url="https://example.supabase.co",service_role_key="secret")
        store._rpc=lambda name,payload:{"project_key":"demo","repository":"owner/repo"}
        store._get=lambda path:[{"manifest":{}}]
        source=store.context_source("run-1")
        self.assertEqual(source["human_decisions"],[])


if __name__=="__main__":
    unittest.main()
