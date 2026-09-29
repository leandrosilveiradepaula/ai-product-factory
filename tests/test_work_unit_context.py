import unittest

from ai_product_factory.work_unit_context import build_context_packet,enforce_write_scopes,path_is_within_scopes


class WorkUnitContextTests(unittest.TestCase):
    def source(self):
        return {
            "project_key":"demo",
            "repository":"owner/repo",
            "change_set_id":"cs",
            "work_unit_id":"wu",
            "plan_task_key":"api",
            "agent_key":"development",
            "wave":1,
            "task":{"title":"API","description":"Implement endpoint","acceptance_criteria":["works"]},
            "assignment":{
                "task_key":"api","agent_key":"development",
                "scope_keys":["src/api/**"],
                "required_capabilities":["implementation"],
                "depends_on":[],
            },
            "repair":{},
            "constraints":["No production merge"],
        }

    def test_context_packet_is_minimal_hashed_and_scope_bounded(self):
        packet=build_context_packet(
            source=self.source(),impact={"confidence":"high","unknowns":[]},
            base_commit="a"*40,branch="factory/cs/api",
        )
        self.assertEqual(packet.version,1)
        self.assertEqual(len(packet.sha256),64)
        self.assertEqual(packet.payload["repository"]["write_scopes"],["src/api/**"])
        self.assertFalse(packet.payload["sandbox"]["secrets_in_context"])
        self.assertNotIn("project_history",packet.payload)

    def test_secret_like_context_is_rejected(self):
        source=self.source()
        source["repair"]={"token":"sk-proj-thismustneverentermodelcontext"}
        with self.assertRaisesRegex(ValueError,"secret-bearing"):
            build_context_packet(source=source,impact={},base_commit="a"*40,branch="factory/cs/api")

    def test_write_scope_enforcement_accepts_children_and_rejects_siblings(self):
        self.assertTrue(path_is_within_scopes("src/api/users.py",("src/api/**",)))
        enforce_write_scopes(("src/api/users.py","src/api/routes/x.py"),("src/api/**",))
        with self.assertRaisesRegex(PermissionError,"outside assigned scopes"):
            enforce_write_scopes(("src/api/users.py","src/auth/session.py"),("src/api/**",))

    def test_empty_write_scope_fails_closed(self):
        with self.assertRaisesRegex(PermissionError,"no explicit write scopes"):
            enforce_write_scopes(("src/api/users.py",),())


if __name__=="__main__":
    unittest.main()
