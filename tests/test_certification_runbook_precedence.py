"""Regression for superseded instructions in Factory certification runbooks."""
from pathlib import Path
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CertificationRunbookPrecedenceTests(unittest.TestCase):
    def read(self,path):
        return (ROOT/path).read_text(encoding="utf-8")

    def test_active_contract_has_no_retired_recovery_steps(self):
        contract=self.read("docs/FINALIZATION_EXECUTION_CONTRACT.md")
        active=contract.split("## 3. Sequência de encerramento vigente",1)[1].split("## 4.",1)[0]
        self.assertIn("CRM Infodive",active)
        self.assertIn("greenfield",active)
        self.assertIn("Não iniciar/reiniciar o projeto parado",active)
        self.assertIn("históricos aposentados",active)
        self.assertNotIn("52998a8f-b478-46b3-9529-08bea72034f3",active)
        self.assertNotIn("60dd6b73-3e98-4da0-bc36-4be6d7562f45",active)
        self.assertNotIn("só usar o procedimento de [recuperação]",active)

    def test_dated_priority_and_no_disposable_production_projects(self):
        agents_doc=self.read("AGENTS.md")
        plan_doc=self.read("PROJECT_PLAN.md")
        agents=agents_doc.split("\n---\n",1)[0]
        plan=plan_doc.split("\n\n",1)[0]
        memory=self.read("MEMORY.md")
        certification_plan=self.read("docs/PLANO_CERTIFICACAO_19_CRITERIOS.md")
        manual=self.read("docs/MANUAL_LIFECYCLE_ACCEPTANCE.md")
        # New priority outranks historical snapshots; both older, stricter
        # controls and the legitimate existing/greenfield requirements remain.
        for scope in (agents,plan):
            self.assertIn("09/11/2026",scope)
            self.assertIn("PLANO_CERTIFICACAO_19_CRITERIOS.md",scope)
        self.assertIn("MEMORY.md",agents)
        self.assertIn("27/10/2026",agents_doc)
        self.assertIn("27/10/2026",plan_doc)
        for scope in (memory,certification_plan):
            self.assertIn("CRM Infodive",scope)
            self.assertIn("greenfield",scope.lower())
            self.assertIn("19",scope)
        self.assertIn("product_ready=true",certification_plan)
        self.assertIn("merge humano",certification_plan.lower())
        self.assertIn("Não criar projetos descartáveis",manual)
        self.assertNotIn("Register a disposable project",manual)
        self.assertNotIn("newly registered disposable project",manual)

    def test_human_gate_and_rollback_boundaries(self):
        doc=self.read("docs/RELEASE_AUTONOMY.md")
        policy=json.loads(self.read("config/factory.release-policy.v1.json"))
        self.assertTrue(policy["production"]["human_release_required"])
        self.assertFalse(policy["production"]["auto_merge_allowed"])
        self.assertTrue(policy["rollback"]["migration_change_requires_verified_rollback"])
        for phrase in ("awaiting_release","operador humano","release observer",
                       "PR de reversão","Preview N/A","rollback.verified=true",
                       "RLS","product_ready=false"):
            self.assertIn(phrase.lower(),doc.lower())
        self.assertIn("não** execução de rollback em produção",doc)

    def test_status_and_operations_link_current_runbook(self):
        self.assertIn("RELEASE_AUTONOMY.md",self.read("docs/OPERATIONS.md")[:1200])
        self.assertIn("RELEASE_AUTONOMY.md",self.read("docs/STATUS.md")[:2400])
        self.assertIn("FINALIZATION_EXECUTION_CONTRACT.md",self.read("docs/OPERATIONS.md")[:1200])

if __name__ == '__main__':
    unittest.main()
