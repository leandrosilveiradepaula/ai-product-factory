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

 def test_all_known_github_mutations_are_revocation_fenced(self):
  github=MagicMock()
  def deny():raise PermissionError("project stopped")
  guarded=_CheckpointedGitHub(github,deny)
  names=("commit_files","create_issue","create_pull_request","create_branch",
         "create_branch_at_sha","ensure_branch_at_sha","dispatch_workflow",
         "close_issue")
  for name in names:
   with self.subTest(method=name):
    with self.assertRaises(PermissionError):
     getattr(guarded,name)("sample")
    getattr(github,name).assert_not_called()

 def test_revoked_checkpoint_prevents_subsequent_model_invocations(self):
  producer=MagicMock()
  state={"active":True}
  def checkpoint():
   if not state["active"]:raise PermissionError("project paused")
  guarded=_CheckpointedProducer(producer,checkpoint)
  guarded.produce("first")
  state["active"]=False
  with self.assertRaises(PermissionError):guarded.produce("second")
  producer.produce.assert_called_once_with("first")

 def test_integration_mutations_are_fenced(self):
  github=MagicMock()
  def deny():raise PermissionError("project stopped")
  guarded=_CheckpointedGitHub(github,deny)
  for name in ("ensure_branch_at_sha","commit_files","create_issue","create_pull_request","dispatch_workflow"):
   with self.subTest(name=name):
    with self.assertRaises(PermissionError):getattr(guarded,name)("test")
    getattr(github,name).assert_not_called()

 def test_integration_control_plane_mutations_are_revocation_fenced(self):
  from ai_product_factory.runtime_cli import _CheckpointedIntegrationStore
  store=MagicMock()
  state={"running":True}
  def checkpoint():
   if not state["running"]:raise PermissionError("project paused")
  guarded=_CheckpointedIntegrationStore(store,checkpoint)
  guarded.complete_integration(change_set_id="one",candidate_commit="sha",changed_files=())
  state["running"]=False
  for name in ("complete_integration","mark_repair_wave_integrated","prepare_release"):
   with self.subTest(method=name):
    with self.assertRaises(PermissionError):getattr(guarded,name)("sample")
  store.complete_integration.assert_called_once()
  store.mark_repair_wave_integrated.assert_not_called()
  store.prepare_release.assert_not_called()

 def test_integration_store_read_methods_remain_available_after_revocation(self):
  from ai_product_factory.runtime_cli import _CheckpointedIntegrationStore
  store=MagicMock()
  def deny():raise PermissionError("stopped")
  guarded=_CheckpointedIntegrationStore(store,deny)
  guarded.frozen_source_commit("change-set")
  store.frozen_source_commit.assert_called_once_with("change-set")
