import unittest
from unittest.mock import patch
from ai_product_factory.runtime_cli import run_direct_once
from ai_product_factory.runtime_auth import AuthKind,RuntimeAuth
class Resolver:
 def __init__(self,kind):self.kind=kind
 def resolve(self):return RuntimeAuth(self.kind,"test",True)
 def resolve_primary_api(self):return RuntimeAuth(self.kind,"test",True)
class Tests(unittest.TestCase):
 def test_direct_fails_before_claim_when_primary_auth_unsupported(self):
  with patch("ai_product_factory.runtime_cli.RuntimeAuthResolver",return_value=Resolver(AuthKind.NONE)),patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue") as queue:
   out=run_direct_once("w")
  self.assertEqual(out["status"],"blocked");queue.assert_not_called()
 def test_direct_empty_queue_does_not_construct_github(self):
  class Q:
   def claim_next(self,w):return None
  env={"FACTORY_PRIMARY_MODEL_ENABLED":"true","FACTORY_MODEL_BUDGET_USD":"5","FACTORY_MODEL_RESERVE_USD":"0.25"}
  health=type("H",(),{"known_cost":0,"unknown_cost_events":0})()
  reader=type("R",(),{"read":lambda self,**kwargs:health})()
  with patch.dict("os.environ",env,clear=True),patch("ai_product_factory.runtime_cli.RuntimeAuthResolver",return_value=Resolver(AuthKind.OPENAI_API_KEY)),patch("ai_product_factory.runtime_cli.SupabaseOperationalHealthReader",return_value=reader),patch("ai_product_factory.runtime_cli.OpenAIResponsesProvider"),patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue",return_value=Q()),patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as gh:
   out=run_direct_once("w")
  self.assertEqual(out["status"],"empty");gh.assert_not_called()
if __name__=="__main__":unittest.main()
