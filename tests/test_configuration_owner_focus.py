"""Configuration should prioritize budget decisions and defer diagnostics."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
PAGE=(ROOT/"apps/console/app/configuration/page.tsx").read_text(encoding="utf-8")
PANEL=(ROOT/"apps/console/app/configuration/cost-policy-panel.tsx").read_text(encoding="utf-8")
CSS=(ROOT/"apps/console/app/product-experience.css").read_text(encoding="utf-8")
HOME=(ROOT/"apps/console/lib/owner-financial-blocker.ts").read_text(encoding="utf-8")
ROUTE=(ROOT/"apps/console/app/api/configuration/cost-policy/route.ts").read_text(encoding="utf-8")
class ConfigurationOwnerFocusTests(unittest.TestCase):
 def test_owner_budget_is_top_level_before_all_advanced_diagnostics(self):
  self.assertLess(PAGE.index("<PrimaryCostPolicyPanel"),PAGE.index("configurationBeyond"))
  self.assertIn('id="orcamento"',PANEL)
  self.assertIn('href:"/configuration"',HOME)
  self.assertIn('id="politicas-avancadas"',PAGE)
  self.assertIn('id="politicas-de-preview"',PAGE)
  self.assertIn('id="dados-tecnicos"',PAGE)
  self.assertIn('className="overviewGrid configOverviewGrid"',PAGE)
  self.assertNotIn('className="configTabs"',PAGE)
  self.assertIn("scroll-margin-top",CSS)

 def test_relevant_costs_and_save_are_visible_before_audit_log(self):
  for text in ('Situação atual','Saldo do teto interno','Reserva por execução paga',
               'Alterar limite interno','Salvar limite','name="budget_usd"',
               'name="reserve_usd"','name="reason"','name="confirm" value="true" required',
               'ConfirmSubmit','primaryCostFeedback'):
   self.assertIn(text,PANEL)
  self.assertLess(PANEL.index('name="budget_usd"'),PANEL.index('className="primaryCostHistory"'))
  self.assertIn('Histórico de alterações (últimas 20)',PANEL)
  self.assertIn('<details className="primaryCostHistory">',PANEL)
  self.assertIn('admin?<form method="POST"',PANEL)
  self.assertIn('requireConsoleAdmin()',ROUTE)
  self.assertIn('origin!==url.origin',ROUTE)
  self.assertIn('name="version" value={policy.version}',PANEL)
  self.assertIn('policy.knownSpendUsd',PANEL)
  self.assertNotIn("15.00",PANEL)
  self.assertNotIn("dark-channel-studio",PANEL)

 def test_nested_diagnostics_are_closed_by_default(self):
  self.assertIn('<details className="configurationDisclosure"',PAGE)
  self.assertIn('<details className="manifestDetails">',PAGE)
  self.assertIn('<pre className="jsonBlock">{JSON.stringify(p.manifest,null,2)}</pre>',PAGE)
  self.assertIn('previewLabel(p.manifest)',PAGE)
  self.assertIn('c.projects.map',PAGE)
  self.assertIn('config.control_plane',PAGE)
  self.assertNotIn('<details className="configurationDisclosure" open',PAGE)
  self.assertIn('grid-template-columns:minmax(0,1fr)',CSS)
if __name__=="__main__":unittest.main()
