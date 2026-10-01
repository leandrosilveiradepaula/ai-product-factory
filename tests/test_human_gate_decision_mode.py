import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261001134930_factory_human_gate_decision_mode.sql"


class HumanGateDecisionModeTests(unittest.TestCase):
    def test_dispatch_v2_persists_pending_gate(self):
        text=MIGRATION.read_text()
        self.assertIn("factory_record_dispatch_decision_v2",text)
        self.assertIn("insert into public.factory_human_gates",text)
        self.assertIn("'execution_approval'",text)
        self.assertIn("human_gate.requested",text)

    def test_decision_only_resolution_never_queues_execution(self):
        text=MIGRATION.read_text()
        decision_block=text.split("if v_decision_only then",1)[1].split("elsif p_resolution='approved' then",1)[0]
        self.assertIn("set status='completed'",decision_block)
        self.assertIn("decision_only_resolved",decision_block)
        self.assertNotIn("queued_execution",decision_block)
        self.assertNotIn("status='queued'",decision_block)

    def test_execution_gate_approval_keeps_existing_queue_semantics(self):
        text=MIGRATION.read_text()
        execution_block=text.split("elsif p_resolution='approved' then",1)[1].split("else",1)[0]
        self.assertIn("status='queued'",execution_block)
        self.assertIn("status='queued_execution'",execution_block)


if __name__=="__main__":
    unittest.main()
