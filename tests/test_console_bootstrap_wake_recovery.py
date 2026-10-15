from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
RECOVERY=(ROOT/"apps/console/lib/intake-worker-recovery.ts").read_text()
APP=(ROOT/"apps/console/lib/github-app.ts").read_text()
ROUTE=(ROOT/"apps/console/app/api/projects/wake-recovery/route.ts").read_text()
PAGE=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()

class Tests(unittest.TestCase):
 def test_admin_only_same_origin_post(self):
  self.assertIn("requireConsoleAdmin()",ROUTE)
  self.assertIn('origin!==url.origin',ROUTE)
  self.assertIn('method="POST"',PAGE)
  self.assertIn('operator.role==="admin"',PAGE)
 def test_only_unclaimed_project_bootstrap_can_wake(self):
  for marker in ("product-bootstrap-v1","project-reconciliation-v1",
   'status=eq.queued','status=eq.created','attempt_count','started_at'):
   self.assertIn(marker,RECOVERY)
  self.assertIn("requestIntakeWorkerWake()",RECOVERY)
  self.assertIn("project.bootstrap.recovery_requested",RECOVERY)
  self.assertIn("15*60*1000",RECOVERY)
  self.assertIn("project.bootstrap.wake_attempted",RECOVERY)
  self.assertIn("if(!prior.ok)",RECOVERY)
  self.assertIn("if(!audit.ok)",RECOVERY)
 def test_read_only_factory_app_installation_probe(self):
  self.assertIn("inspectFactoryWakeAppInstallation",APP)
  self.assertIn("permissions?.contents",APP)
  self.assertIn('if(status===404)return "not_installed"',APP)
  self.assertIn("permissions_missing",APP)
 def test_never_bypass_paid_or_prod_gates(self):
  for x in ("merge_pull_request","FACTORY_PRIMARY_MODEL_ENABLED","OPENAI_API_KEY","NEXT_PUBLIC_"):
   self.assertNotIn(x,RECOVERY+ROUTE)

if __name__=="__main__":
 unittest.main()
