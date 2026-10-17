"""Offline side-effect fencing tests; never contact Supabase, GitHub or models."""
import unittest
from unittest.mock import MagicMock
from ai_product_factory.runtime_cli import _CheckpointedProducer, _CheckpointedGitHub

class RoutedExecutionCheckpointTests(unittest.TestCase):
 def test_model_invocation_is_denied_on_revoked_epoch(self):
  producer=MagicMock()
  def deny():raise PermissionError("routed run capability revoked")
  with self.assertRaises(PermissionError):
   _CheckpointedProducer(producer,deny).produce(object())
  producer.produce.assert_not_called()

 def test_github_commit_is_denied_on_revoked_epoch(self):
  github=MagicMock()
  def deny():raise PermissionError("routed run capability revoked")
  with self.assertRaises(PermissionError):
   _CheckpointedGitHub(github,deny).commit_files("branch",{"file":"content"},message="x")
  github.commit_files.assert_not_called()

 def test_checkpoint_is_evaluated_for_each_write(self):
  github=MagicMock()
  state={"valid":True,"checks":0}
  def check():
   state["checks"]+=1
   if not state["valid"]:raise PermissionError("revoked")
  guarded=_CheckpointedGitHub(github,check)
  guarded.commit_files("branch",{"x":"y"},message="x")
  state["valid"]=False
  with self.assertRaises(PermissionError):
   guarded.commit_files("branch",{"x":"z"},message="x")
  self.assertEqual(github.commit_files.call_count,1)
  self.assertEqual(state["checks"],2)

 def test_read_only_methods_are_not_blocked(self):
  github=MagicMock()
  guarded=_CheckpointedGitHub(github,lambda:(_ for _ in ()).throw(PermissionError("revoked")))
  guarded.get_branch_sha("main")
  github.get_branch_sha.assert_called_once_with("main")
