"""A Codex auth signal alone cannot allow competing automatic/manual claimers."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
PY=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
SQL=(ROOT/"supabase/migrations/20261002144500_manual_codex_handoff.sql")
class CodexClaimIsolationRegression(unittest.TestCase):
 def test_codex_auto_dispatch_inert_while_db_claimers_overlap(self):
  body=PY.split("def allowed_dispatch_routes()",1)[1].split("\ndef run_dispatch_once(",1)[0]
  self.assertNotIn('FACTORY_DISPATCH_CODEX_READY',body)
  self.assertIn('FACTORY_CODEX_MANUAL_FALLBACK_ENABLED',body)
  routed=PY.split("def run_dispatch_once(",1)[1].split("\ndef main(",1)[0]
  self.assertIn("automatic Codex dispatch requires atomic execution-mode isolation",routed)
 def test_no_auto_merge_or_paid_test_invocation(self):
  self.assertNotIn("merge_pull_request",PY)
  self.assertNotIn("codex exec",PY)
if __name__=="__main__":unittest.main()
