"""Cold-start barrier regressions; all tests offline, no real API tokens."""
import unittest
from ai_product_factory.private_model_warmup import WarmupBlocked, warmup_if_pending

BASE={
    "FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud",
    "FACTORY_PRIMARY_MODEL_ENABLED":"true",
    "FACTORY_INFODIVE_VPS_WORKER_ENABLED":"true",
    "FACTORY_SQL_INFODIVE_ENABLED":"true",
    "FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED":"true",
    "FACTORY_SQL_INFODIVE_BASE_URL":"http://10.66.66.1",
    "FACTORY_SQL_INFODIVE_HTTP_HOST":"chat.internal",
    "FACTORY_SQL_INFODIVE_MODEL":"SQL-InfoDive",
    "FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP":"true",
    "FACTORY_SQL_INFODIVE_PRICING_APPROVED":"true",
    "FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION":"0",
    "FACTORY_SQL_INFODIVE_OUTPUT_USD_PER_MILLION":"0",
    "FACTORY_SQL_INFODIVE_API_KEY":"fake-for-offline-tests-only",
}

class WarmupTests(unittest.TestCase):
    def make(self,env=None,pending=True,reply=None,budget=None,route=None):
        calls=[]
        def transport(config,key):
            calls.append("post")
            self.assertEqual(config.model_id,"SQL-InfoDive")
            self.assertEqual(key,"fake-for-offline-tests-only")
            return reply if reply is not None else (
                200,{"choices":[{"message":{"content":"OK"}}],
                     "usage":{"prompt_tokens":11,"completion_tokens":2}})
        ret=lambda: calls.append("budget") if budget is None else budget()
        via=lambda *a,**k: calls.append("route") if route is None else route()
        return warmup_if_pending(
            BASE if env is None else env,
            pending=lambda _: pending,c apacity=ret,
            route=via,request=transport,
        ),calls

    def test_no_pending_work_no_bearer_no_call(self):
        d={k:v for k,v in BASE.items() if k!="FACTORY_SQL_INFODIVE_API_KEY"}
        state,calls=self.make(d,pending=False)
        self.assertEqual(state["status"],"idle")
        self.assertFalse(state["model_invoked"])
        self.assertEqual(calls,[])

    def test_valid_zero_cost_private_route(self):
        state,calls=self.make()
        self.assertEqual(calls,["budget","route","post"])
        self.assertEqual(state["status"],"warmed")
        self.assertEqual(state["marginal_cost_usd"],"0")
        self.assertFalse(state["run_claimed"])
        self.assertNotIn(BASE["FACTORY_SQL_INFODIVE_API_KEY"],str(state))

    def test_nonzero_or_unapproved_pricing_never_calls(self):
        for override in (
            {"FACTORY_SQL_INFODIVE_PRICING_APPROVED":"false"},
            {"FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION":"0.001"},
            {"FACTORY_SQL_INFODIVE_OUTPUT_USD_PER_MILLION":"1"},
        ):
            with self.subTest(override=override):
                with self.assertRaises(WarmupBlocked):
                    self.make({**BASE,**override})

    def test_disabled_provider_never_calls(self):
        for key,value in (
            ("FACTORY_PRIMARY_MODEL_ENABLED","false"),
            ("FACTORY_PRIMARY_MODEL_PROVIDER","openai"),
            ("FACTORY_INFODIVE_VPS_WORKER_ENABLED","false"),
        ):
            with self.subTest(key=key),self.assertRaises(WarmupBlocked):
                self.make({**BASE,key:value},pending=False)

    def test_missing_bearer_is_blocked(self):
        with self.assertRaises(WarmupBlocked):
            self.make({k:v for k,v in BASE.items()
                       if k!="FACTORY_SQL_INFODIVE_API_KEY"})

    def test_route_or_budget_failure_is_sanitized(self):
        for failure in ("budget","route"):
            failing=lambda: (_ for _ in ()).throw(RuntimeError("fake-secret"))
            try:
                self.make(budget=failing if failure=="budget" else None,
                          route=lambda: failing() if failure=="route" else None)
            except WarmupBlocked as error:
                self.assertNotIn("fake-secret",str(error))
            else:
                self.fail("unverified route or budget passed")

    def test_invalid_model_usage_never_succeeds(self):
        for payload in (
            (401,{"error":"fake-secret"}),
            (200,{"choices":[{"message":{"content":"OK"}}]}),
            (200,{"choices":[{"message":{"content":""}}],
                   "usage":{"prompt_tokens":3,"completion_tokens":1}}),
            (200,{"choices":[{"message":{"content":"OK"}}],
                   "usage":{"prompt_tokens":True,"completion_tokens":1}}),
        ):
            with self.subTest(status=payload[0]),self.assertRaises(WarmupBlocked):
                self.make(reply=payload)


if __name__=="__main__":
    unittest.main()
