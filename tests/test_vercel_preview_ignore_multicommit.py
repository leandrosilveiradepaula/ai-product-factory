"""Real local-git tests of Vercel's ignored-build command; no Vercel/API calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"apps/console/vercel.json"

class VercelPreviewIgnoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.repo=Path(self.tmp.name)
  self.app=self.repo/"apps/console"
  self.app.mkdir(parents=True)
  (self.repo/"config").mkdir()
  self.git("init","-b","main")
  self.git("config","user.email","ci@example.invalid")
  self.git("config","user.name","CI")
  (self.app/"view.tsx").write_text("v1")
  (self.repo/"config/factory.release-policy.v1.json").write_text("{}")
  self.git("add",".")
  self.git("commit","-m","baseline")
  self.base=self.git("rev-parse","HEAD").stdout.strip()
  (self.app/"view.tsx").write_text("v2")
  self.git("add",".")
  self.git("commit","-m","console update")
  (self.repo/"README.md").write_text("README")
  self.git("add",".")
  self.git("commit","-m","docs only followup")
  self.head=self.git("rev-parse","HEAD").stdout.strip()
  self.command=json.loads(CONFIG.read_text())["ignoreCommand"]

 def tearDown(self):self.tmp.cleanup()

 def git(self,*args):
  result=subprocess.run(["git",*args],cwd=self.repo,capture_output=True,text=True)
  if result.returncode:raise AssertionError(result.stderr)
  return result

 def run_gate(self,branch,previous=""):
  env={**os.environ,"VERCEL_GIT_COMMIT_REF":branch,"VERCEL_GIT_PREVIOUS_SHA":previous}
  return subprocess.run(["sh","-c",self.command],cwd=self.app,env=env,capture_output=True,text=True).returncode

 def test_multi_commit_candidate_detects_earlier_console_change(self):
  self.assertEqual(self.run_gate("preview/pr-123",self.base),1)

 def test_repeated_candidate_without_console_changes_is_ignored(self):
  self.assertEqual(self.run_gate("preview/pr-123",self.head),0)

 def test_first_preview_is_built_only_on_promoted_candidate_ref(self):
  self.assertEqual(self.run_gate("preview/pr-123"),1)
  self.assertEqual(self.run_gate("preview/scratch"),0)
  self.assertEqual(self.run_gate("preview/pr-unknown"),0)

 def test_invalid_or_unavailable_previous_sha_does_not_fake_verification(self):
  self.assertEqual(self.run_gate("preview/pr-123","a"*40),1)

 def test_production_non_console_docs_change_is_skipped(self):
  self.assertEqual(self.run_gate("main",self.base),0)

 def test_production_console_change_is_built(self):
  (self.app/"view.tsx").write_text("v3")
  self.git("add",".")
  self.git("commit","-m","production UI")
  self.assertEqual(self.run_gate("main"),1)

if __name__=="__main__":unittest.main()
