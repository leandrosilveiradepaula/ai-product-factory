from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/"apps"/"console"/"app"/"gates"/"page.tsx"
CONTROL=ROOT/"apps"/"console"/"lib"/"control-plane.ts"


class ConsoleGateContextTests(unittest.TestCase):
    def test_structured_planning_reasons_are_rendered_as_decisions(self):
        text=PAGE.read_text()
        self.assertIn("function GateReasons",text)
        self.assertIn("reason.question",text)
        self.assertIn("reason.why_needed",text)
        self.assertIn("reason.decision_key",text)
        self.assertIn("reason.decision_kind",text)
        self.assertNotIn("value.join(\", \")",text)
        self.assertIn("<GateReasons value={g.reasons}/>",text)

    def test_planning_answer_uses_multiline_field_with_guidance(self):
        text=PAGE.read_text()
        self.assertIn('<textarea name="note" required rows={5}',text)
        self.assertIn("Responde cada decisão acima",text)

    def test_only_live_awaiting_human_gate_is_actionable(self):
        control=CONTROL.read_text()
        self.assertIn('runStatus==="awaiting_human"',control)
        self.assertIn('taskStatus==="awaiting_human"',control)
        self.assertIn("actionable:boolean",control)
        page=PAGE.read_text()
        self.assertIn('g.status==="pending"&&g.actionable',page)
        self.assertIn('label={g.status==="pending"&&!g.actionable?"histórico":undefined}',page)

    def test_stale_pending_gates_do_not_count_as_pending(self):
        text=PAGE.read_text()
        self.assertIn('const pending=gates.filter(g=>g.status==="pending"&&g.actionable)',text)
        self.assertIn("const history=gates.filter",text)
        self.assertIn("orderedGates=[...pending,...history]",text)


if __name__=="__main__":
    unittest.main()
