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

    def test_planning_answer_uses_one_guided_field_per_decision(self):
        text=PAGE.read_text()
        self.assertIn('name={`decision_response_${index}`}',text)
        self.assertIn('name={`decision_key_${index}`}',text)
        self.assertIn("O que você precisa decidir",text)
        self.assertIn("Por que isso é necessário",text)
        self.assertIn("Sua resposta",text)
        self.assertIn("Detalhes técnicos",text)
        self.assertIn("Registrar respostas e continuar",text)

    def test_server_action_composes_all_planning_answers(self):
        text=PAGE.read_text()
        self.assertIn('formData.get(`decision_key_${index}`)',text)
        self.assertIn('formData.get(`decision_response_${index}`)',text)
        self.assertIn('responses.push(`${index+1}. ${key}',text)
        self.assertIn('responses.join("\\n\\n")',text)

    def test_only_live_awaiting_human_gate_is_actionable(self):
        control=CONTROL.read_text()
        self.assertIn('runStatus==="awaiting_human"',control)
        self.assertIn('taskStatus==="awaiting_human"',control)
        self.assertIn("actionable:boolean",control)
        page=PAGE.read_text()
        self.assertIn('g.status==="pending"&&g.actionable',page)
        self.assertIn('history.map(g=><article className="gateHistoryItem"',page)
        self.assertIn('label={g.status==="pending"?"substituído":undefined}',page)

    def test_stale_pending_gates_do_not_count_as_pending(self):
        text=PAGE.read_text()
        self.assertIn('const pending=gates.filter(g=>g.status==="pending"&&g.actionable)',text)
        self.assertIn("const history=gates.filter",text)
        self.assertIn("pending.map(g=><article",text)
        self.assertIn('details className="gateHistory"',text)

    def test_gate_inbox_separates_actionable_work_from_history(self):
        text=PAGE.read_text()
        self.assertIn("pending.map(g=><article",text)
        self.assertIn('details className="gateHistory"',text)
        self.assertIn("gates resolvidos ou substituídos",text)
        self.assertNotIn("orderedGates.map",text)

    def test_gate_cards_show_human_context_before_technical_ids(self):
        text=PAGE.read_text()
        self.assertIn('className="gateContextHero"',text)
        self.assertIn("Abrir projeto",text)
        self.assertIn("Ver execução",text)
        self.assertIn('details className="gateTechnicalMeta"',text)
        self.assertIn("Contexto técnico",text)


if __name__=="__main__":
    unittest.main()
