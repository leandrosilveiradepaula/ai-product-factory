"""Operator-first Factory Console and real read-only Kanban contract.
No mock board, no auto-merge, no implicit paid model or database mutation.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"apps/console/app"
HOME=(APP/"page.tsx").read_text(encoding="utf-8")
BOARD=(APP/"deliveries/page.tsx").read_text(encoding="utf-8")
DETAIL=(APP/"deliveries/[id]/page.tsx").read_text(encoding="utf-8")
READER=(ROOT/"apps/console/lib/delivery-board.ts").read_text(encoding="utf-8")
PRESENTATION=(ROOT/"apps/console/lib/operator-home.ts").read_text(encoding="utf-8")
NAV=(APP/"nav.tsx").read_text(encoding="utf-8")
SHELL=(APP/"shell.tsx").read_text(encoding="utf-8")
LAYOUT=(APP/"layout.tsx").read_text(encoding="utf-8")
STYLE=(APP/"operator.css").read_text(encoding="utf-8")
CI=(ROOT/".github/workflows/console.yml").read_text(encoding="utf-8")

class OperatorExperienceTests(unittest.TestCase):
 def test_home_starts_with_three_real_goals_not_technical_incidents(self):
  for label in ("Criar um produto", "Melhorar um produto", "Acompanhar entregas"):
   self.assertIn(label, HOME)
  for destination in ('href="/projects/new"', 'href="/projects"', 'href="/deliveries"'):
   self.assertIn(destination,HOME)
  self.assertLess(HOME.index('className="operatorWelcome"'),HOME.index('className="operatorDiagnostics"'))
  self.assertIn('details className="operatorDiagnostics"',HOME)
  self.assertNotIn("incidents.map",HOME)
  self.assertNotIn("i.error",HOME)
  self.assertNotIn("dashboard.pendingGates",HOME)
  self.assertIn('getHumanGates(100,true)',HOME)
  self.assertIn('getGitHubAppInstallActions()',HOME)
  self.assertIn('getGitHubAppStatus()',HOME)
  self.assertIn('summarizeOperatorAttention(',HOME)
 def test_four_destinations_on_desktop_and_mobile(self):
  for label in ('label:"Início"', 'label:"Projetos"', 'label:"Entregas"', 'label:"Decisões"'):
   self.assertIn(label,NAV)
  self.assertIn('href:"/deliveries"',NAV)
  self.assertIn('pathname.startsWith("/deliveries")',SHELL)
  self.assertIn('>Entregas</Link>',SHELL)
  self.assertIn('pendência para revisar',SHELL)
  self.assertIn('repeat(4,minmax(0,1fr))',STYLE)
 def test_readonly_board_uses_authoritative_data_and_integrity_guards(self):
  for table in ('"factory_projects"', '"factory_tasks"', '"factory_runs"'):
   self.assertIn(table,READER)
  self.assertIn("getHumanGates(100,true)",READER)
  self.assertIn("requireConsoleOperator()",READER)
  self.assertIn('cache:"no-store"',READER)
  self.assertIn("rootOf(task,byId)",READER)
  self.assertIn("seen.has(current.parent_task_id)",READER)
  self.assertIn("parent.project_id!==task.project_id",READER)
  self.assertIn("excede limite verificado",READER)
  self.assertIn('export type DeliveryLane=',READER)
  self.assertIn('blockedStatuses',READER)
  for label in ('A fazer','Em execução','Validando','Aguardando você','Bloqueado','Encerrado'):
   self.assertIn(label,READER)
  for sensitive in ('method:"POST"','apply_migration','mergeReadyReleaseFromConsole','FACTORY_PRIMARY_MODEL_ENABLED'):
   self.assertNotIn(sensitive,READER)
 def test_board_is_real_navigation_not_manual_movable_kanban(self):
  self.assertIn('getDeliveryBoard()',BOARD)
  self.assertIn('href="/gates"',BOARD)
  self.assertIn('"/deliveries/"+item.id',BOARD)
  self.assertIn('"/projects/"+item.projectKey+"/request"',DETAIL)
  self.assertIn('href="/deployments"',DETAIL)
  self.assertIn('getDeliveryBoard()',DETAIL)
  self.assertIn('Etapas e evidências técnicas',DETAIL)
  self.assertIn('"/runs/"+item.latestRunId',BOARD)
  self.assertIn("items.slice(8)",BOARD)
  self.assertIn('aria-label="Filtrar entregas por produto"',BOARD)
  self.assertIn("Você não precisa mover cartões",BOARD)
  self.assertIn('não comprova aprovação de qualidade',BOARD)
  self.assertNotIn("draggable",BOARD)
  self.assertNotIn("onDrop",BOARD)
 def test_responsive_accessible_styles_and_compiler_regression(self):
  self.assertIn('import "./operator.css";',LAYOUT)
  for style in (".operatorChoices", ".operatorChoice:focus-visible", ".deliveryBoard",
                ".deliveryCard", ".deliveryFilter.active", "@media(max-width:760px)"):
   self.assertIn(style,STYLE)
  self.assertIn("node ../../scripts/test_console_operator_delivery_runtime.cjs",CI)

if __name__=="__main__":
 unittest.main()
