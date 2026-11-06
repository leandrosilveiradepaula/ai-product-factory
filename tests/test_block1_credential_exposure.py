import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];s=importlib.util.spec_from_file_location("audit",ROOT/"scripts"/"audit_block1_credential_exposure.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class CredentialExposureTests(unittest.TestCase):
 def test_current_console_has_no_privileged_public_flow(self):
  r=m.audit(ROOT);self.assertFalse(r["credential_exposure_detected"]);self.assertFalse(r["security_certified"]);self.assertGreater(r["console_files_scanned"],0)
 def test_public_route_secret_flow_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"apps/console/app/api/x";p.mkdir(parents=True);(p/"route.ts").write_text('export function GET(){return Response.json({x:process.env.SUPABASE_SECRET_KEY})}')
   r=m.audit(Path(d));self.assertTrue(r["credential_exposure_detected"])
