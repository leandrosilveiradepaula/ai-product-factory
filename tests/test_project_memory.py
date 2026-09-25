import unittest

from ai_product_factory.project_memory import (
    ProjectMemory,
    latest_decision,
    parse_memory,
    update_current_state,
)


class ProjectMemoryTests(unittest.TestCase):
    def memory(self):
        return ProjectMemory(
            product={"name": "Demo", "goal": "Do X"},
            architecture={"style": "service"},
            current_state={"stage": "planning", "status": "active"},
            decisions=(
                {"id": "d1", "type": "database", "decision": "postgres", "created_at": "2026-01-01"},
                {"id": "d2", "type": "database", "decision": "supabase", "created_at": "2026-02-01"},
            ),
        )

    def test_round_trip(self):
        m = self.memory()
        parsed = parse_memory(m.to_files())
        self.assertEqual(parsed.product["name"], "Demo")
        self.assertEqual(len(parsed.decisions), 2)

    def test_latest_decision(self):
        d = latest_decision(self.memory(), "database")
        self.assertEqual(d["decision"], "supabase")

    def test_update_state(self):
        m = update_current_state(self.memory(), stage="implementation", head_sha="abc", status="running")
        self.assertEqual(m.current_state["stage"], "implementation")
        self.assertEqual(m.current_state["head_sha"], "abc")
        self.assertIn("updated_at", m.current_state)

    def test_missing_required_fields_fail(self):
        with self.assertRaises(ValueError):
            ProjectMemory(product={}, architecture={}, current_state={"stage": "x"}).validate()
        with self.assertRaises(ValueError):
            ProjectMemory(product={"name": "x"}, architecture={}, current_state={}).validate()

    def test_unsafe_decision_id_is_rejected(self):
        m = ProjectMemory(
            product={"name": "x"},
            architecture={},
            current_state={"stage": "planning"},
            decisions=({"id": "../bad", "decision": "x"},),
        )
        with self.assertRaises(ValueError):
            m.to_files()


if __name__ == "__main__":
    unittest.main()
