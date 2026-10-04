import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261004185900_materialize_planning_decisions.sql"
GATES_PAGE=ROOT/"apps"/"console"/"app"/"gates"/"page.tsx"


class PlanningDecisionGateMigrationTests(unittest.TestCase):
    def test_planning_decisions_create_durable_human_gate_before_backlog(self):
        text=MIGRATION.read_text()
        planning=text.split("else\n    v_decisions",1)[1].split("insert into public.factory_audit_events(",1)[0]
        self.assertIn("factory_human_gates",planning)
        self.assertIn("'planning_decision'",planning)
        self.assertIn("'awaiting_human'",planning)
        self.assertIn("jsonb_array_length(v_decisions)>0",planning)
        decision_branch=planning.split("if jsonb_array_length(v_decisions)>0 then",1)[1].split("else",1)[0]
        self.assertNotIn("v_created_tasks:=v_created_tasks+1",decision_branch)

    def test_planning_decision_approval_requires_explicit_answer_and_requeues_reconciliation(self):
        text=MIGRATION.read_text()
        self.assertIn("planning decision requires an explicit response",text)
        self.assertIn("'human_decisions'",text)
        self.assertIn("'planning-decision'",text)
        self.assertIn("jsonb_build_array('reconciliation','gap_analysis','planning')",text)
        self.assertIn("'planning_reconciliation_queued'",text)

    def test_production_merge_semantics_are_not_added_to_planning_decision_migration(self):
        text=MIGRATION.read_text().lower()
        self.assertNotIn("merge pull",text)
        self.assertNotIn("auto_merge",text)
        self.assertNotIn("github merge",text)

    def test_console_requires_response_for_planning_decision(self):
        text=GATES_PAGE.read_text()
        self.assertIn('gateType==="planning_decision"&&resolution==="approved"&&!note',text)
        self.assertIn('name="note" required',text)
        self.assertIn("Registrar decisão e continuar",text)


if __name__=="__main__":
    unittest.main()
