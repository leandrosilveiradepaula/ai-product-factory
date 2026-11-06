import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts" / "audit_block1_credential_exposure.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CredentialExposureTests(unittest.TestCase):
 def write(self, root, relative, source):
  path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source,encoding="utf-8")
 def test_current_console_has_no_privileged_public_flow(self):
  receipt=module.audit(ROOT);self.assertFalse(receipt["credential_exposure_detected"]);self.assertFalse(receipt["security_certified"]);self.assertGreater(receipt["console_files_scanned"],0);self.assertGreater(receipt["client_entrypoints_scanned"],0)
 def test_public_route_secret_flow_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.write(root,"apps/console/app/api/health/route.ts","export const GET=()=>Response.json(process.env.SUPABASE_SECRET_KEY)");self.assertTrue(module.audit(root)["credential_exposure_detected"])
 def test_client_import_transitively_reaching_secret_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.write(root,"apps/console/app/page.tsx","'use client'; import {token} from '@/lib/a'; export default function Page(){return <p>{token}</p>}");self.write(root,"apps/console/lib/a.ts","export {token} from './b'");self.write(root,"apps/console/lib/b.ts","export const token=process.env['FACTORY_RELEASE_GITHUB_TOKEN']");receipt=module.audit(root);self.assertTrue(receipt["credential_exposure_detected"]);self.assertEqual(receipt["findings"][0]["source_path"],"apps/console/lib/b.ts")
 def test_next_public_secret_name_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.write(root,"apps/console/app/page.tsx","'use client'; export default function Page(){return <p>{process.env.NEXT_PUBLIC_OPENAI_API_KEY}</p>}");self.assertTrue(module.audit(root)["credential_exposure_detected"])
 def test_privileged_route_without_operator_or_hmac_guard_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.write(root,"apps/console/app/api/x/route.ts","import {token} from '@/lib/a'; export const GET=()=>Response.json({ok:true})");self.write(root,"apps/console/lib/a.ts","export const token=process.env.FACTORY_RELEASE_GITHUB_TOKEN");receipt=module.audit(root);self.assertTrue(receipt["credential_exposure_detected"]);self.assertEqual(receipt["findings"][0]["kind"],"privileged_environment_reachable_from_unprotected_route")
 def test_hmac_guard_allows_server_only_webhook_path(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.write(root,"apps/console/app/api/x/route.ts","import {token} from '@/lib/a'; export async function POST(){await authenticateGitHubWebhook(); return Response.json({ok:true})}");self.write(root,"apps/console/lib/a.ts","export const token=process.env.FACTORY_RELEASE_GITHUB_TOKEN");self.assertFalse(module.audit(root)["credential_exposure_detected"])
 def test_guard_in_one_http_method_cannot_authorize_another(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.write(root,"apps/console/app/api/x/route.ts","import {token} from '@/lib/a'; export async function POST(){await authenticateGitHubWebhook(); return Response.json({ok:true})} export async function GET(){return Response.json({ok:true})}");self.write(root,"apps/console/lib/a.ts","export const token=process.env.FACTORY_RELEASE_GITHUB_TOKEN");receipt=module.audit(root);self.assertTrue(receipt["credential_exposure_detected"]);self.assertEqual(receipt["findings"][0]["unguarded_handlers"],["GET"])
 def test_405_handler_cannot_be_confused_with_a_credential_flow(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.write(root,"apps/console/app/api/x/route.ts","import {token} from '@/lib/a'; export function GET(){return Response.json({error:'method not allowed'},{status:405})} export async function POST(){await authenticateGitHubWebhook(); return Response.json({ok:true})}");self.write(root,"apps/console/lib/a.ts","export const token=process.env.FACTORY_RELEASE_GITHUB_TOKEN");self.assertFalse(module.audit(root)["credential_exposure_detected"])
