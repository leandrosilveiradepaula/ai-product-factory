"""Routed epoch RPC contract tests with isolated network and credentials."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from ai_product_factory.routed_execution_epoch import assert_routed_epoch
from ai_product_factory.supabase_server import SupabaseServerConfig

class Response:
 def __init__(self,status):self.status=status
 def __enter__(self):return self
 def __exit__(self,*args):return False

class RoutedEpochTests(unittest.TestCase):
 def setUp(self):
  cfg=SupabaseServerConfig(url="https://example.supabase.co",key="sb_secret_test",headers={"apikey":"sb_secret_test"})
  p=patch("ai_product_factory.routed_execution_epoch.resolve_supabase_server_config",return_value=cfg)
  p.start();self.addCleanup(p.stop)

 def test_void_rpc_accepts_204_and_200(self):
  for status in (200,204):
   with self.subTest(status=status):
    with patch("ai_product_factory.routed_execution_epoch.urllib.request.urlopen",return_value=Response(status)) as call:
     assert_routed_epoch("project",1,"run","worker")
     request=call.call_args.args[0]
     self.assertEqual(request.get_method(),"POST")
     self.assertEqual(request.headers["Apikey"],"sb_secret_test")
     self.assertNotIn("Authorization",request.headers)
     self.assertEqual(json.loads(request.data)["p_generation"],1)

 def test_invalid_epoch_never_reaches_network(self):
  for generation in (None,0,-1,False,"1"):
   with self.subTest(generation=generation):
    with patch("ai_product_factory.routed_execution_epoch.urllib.request.urlopen") as call:
     with self.assertRaises(PermissionError):
      assert_routed_epoch("project",generation,"run","worker")
     call.assert_not_called()

 def test_denial_and_network_failure_fail_closed(self):
  for error in (HTTPError("https://example.supabase.co",409,"revoked",{},io.BytesIO()),URLError("offline")):
   with self.subTest(error=type(error).__name__):
    with patch("ai_product_factory.routed_execution_epoch.urllib.request.urlopen",side_effect=error):
     with self.assertRaises(PermissionError):
      assert_routed_epoch("project",1,"run","worker")

 def test_unexpected_success_code_is_denied(self):
  with patch("ai_product_factory.routed_execution_epoch.urllib.request.urlopen",return_value=Response(202)):
   with self.assertRaises(PermissionError):
    assert_routed_epoch("project",1,"run","worker")
