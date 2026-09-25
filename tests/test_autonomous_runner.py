import unittest
from unittest.mock import patch
from ai_product_factory.runtime_cli import run_product_once,run_dispatch_once

class Result:
 status=type("S",(),{"value":"completed"})();error=None
class Worker:
 def __init__(self,**kw):pass
 def run_once(self):return Result()
class Decision:
 execution=type("E",(),{"route":type("R",(),{"value":"direct"})(),"human_gate_required":False,"codex":type("C",(),{"level":0})()})()
class Dispatch:
 def dispatch_next(self,key):return Decision()

class Tests(unittest.TestCase):
 def test_product_blocked_auth_is_non_destructive_status(self):
  with patch("ai_product_factory.runtime_cli.build_handler",side_effect=RuntimeError("missing")):
   self.assertEqual(run_product_once("w")["status"],"blocked")
 def test_dispatch_reports_route(self):
  with patch("ai_product_factory.runtime_cli.SupabaseBacklogDispatch",return_value=Dispatch()):
   out=run_dispatch_once("p")
  self.assertEqual(out["route"],"direct");self.assertFalse(out["human_gate_required"])
if __name__=="__main__":unittest.main()
