import unittest

from ai_product_factory.change_set_store import SupabaseChangeSetStore


class ChangeSetStoreContextTests(unittest.TestCase):
    def test_context_source_enriches_durable_human_decisions_from_project_manifest(self):
        store=SupabaseChangeSetStore(url="https://example.supabase.co",service_role_key="secret")
        store._rpc=lambda name,payload:{
            "project_key":"crm-infodive",
            "repository":"owner/repo",
            "task":{"title":"debug-route-remediation"},
        }
        seen=[]
        def get(path):
            seen.append(path)
            return [{"manifest":{"human_decisions":[{"gate_id":"g1","response":"Authorize /debug only"}]}}]
        store._get=get
        source=store.context_source("run-1")
        self.assertEqual(source["human_decisions"],[{"gate_id":"g1","response":"Authorize /debug only"}])
        self.assertIn("project_key=eq.crm-infodive",seen[0])

    def test_context_source_defaults_to_empty_durable_decisions(self):
        store=SupabaseChangeSetStore(url="https://example.supabase.co",service_role_key="secret")
        store._rpc=lambda name,payload:{"project_key":"demo","repository":"owner/repo"}
        store._get=lambda path:[{"manifest":{}}]
        source=store.context_source("run-1")
        self.assertEqual(source["human_decisions"],[])


if __name__=="__main__":
    unittest.main()
