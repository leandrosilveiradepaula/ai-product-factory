"""Deterministic regressions for the authoritative Control Plane cost policy."""
import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_factory.primary_cost_config import (
    PrimaryCostPolicy, SupabasePrimaryCostPolicyReader,
    parse_primary_cost_policy, require_primary_cost_capacity,
)

ROW={"policy_key":"primary","budget_usd":"10.0000","reserve_usd":"0.5000","version":1}


class Response:
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.payload).encode()


class PrimaryCostPolicyTests(unittest.TestCase):
    def test_reads_exact_one_policy_through_privileged_server(self):
        with patch("urllib.request.urlopen",return_value=Response([ROW])) as call:
            policy=SupabasePrimaryCostPolicyReader(
                url="https://test.supabase.co",secret_key="sb_secret_test",
            ).read()
        self.assertEqual(policy,PrimaryCostPolicy(Decimal("10"),Decimal("0.5"),1))
        req=call.call_args.args[0]
        self.assertEqual(req.get_method(),"GET")
        self.assertIn("factory_primary_cost_policy",req.full_url)
        self.assertIn("policy_key=eq.primary&limit=2",req.full_url)
        self.assertEqual(req.get_header("Apikey"),"sb_secret_test")
        self.assertIsNone(req.get_header("Authorization"))

    def test_missing_duplicate_malformed_or_stale_policy_rejected(self):
        for body in (
            [],[ROW,ROW],[{"policy_key":"other",**{k:v for k,v in ROW.items() if k!="policy_key"}}],
            [{**ROW,"budget_usd":"0"}],[{**ROW,"budget_usd":"NaN"}],
            [{**ROW,"reserve_usd":"11"}],[{**ROW,"reserve_usd":None}],
            [{**ROW,"version":0}],[{**ROW,"version":True}],
            [{**ROW,"budget_usd":"1.12345"}],[{**ROW,"budget_usd":"100001"}],
        ):
            with self.subTest(body=body),self.assertRaises(RuntimeError):
                parse_primary_cost_policy(body)

    def test_cumulative_budget_and_reservation_enforced(self):
        policy_reader=SimpleNamespace(read=lambda:parse_primary_cost_policy([ROW]))
        health=SimpleNamespace(read=lambda *,budget:SimpleNamespace(known_cost=Decimal("9.4"),unknown_cost_events=0))
        policy=require_primary_cost_capacity(policy_reader=policy_reader,health_reader=health)
        self.assertEqual(policy.reserve_usd,Decimal("0.5"))
        health.read=lambda *,budget:SimpleNamespace(known_cost=Decimal("9.6"),unknown_cost_events=0)
        with self.assertRaises(PermissionError):
            require_primary_cost_capacity(policy_reader=policy_reader,health_reader=health)

    def test_paid_cost_unknown_blocks(self):
        policy_reader=SimpleNamespace(read=lambda:parse_primary_cost_policy([ROW]))
        health=SimpleNamespace(read=lambda *,budget:SimpleNamespace(known_cost=Decimal("0"),unknown_cost_events=1))
        with self.assertRaisesRegex(PermissionError,"unknown-cost"):
            require_primary_cost_capacity(policy_reader=policy_reader,health_reader=health)

    def test_unavailable_policy_rejected_before_ledger(self):
        reader=SimpleNamespace(read=lambda:parse_primary_cost_policy([]))
        ledger=SimpleNamespace(read=lambda *,budget:self.fail("ledger queried after missing policy"))
        with self.assertRaisesRegex(RuntimeError,"missing or duplicated"):
            require_primary_cost_capacity(policy_reader=reader,health_reader=ledger)

    def test_policy_reloaded_per_preflight(self):
        state={"budget_usd":"10.0000"}
        reader=SimpleNamespace(read=lambda:parse_primary_cost_policy([{**ROW,**state}]))
        health=SimpleNamespace(read=lambda *,budget:SimpleNamespace(known_cost=Decimal("3"),unknown_cost_events=0))
        require_primary_cost_capacity(policy_reader=reader,health_reader=health)
        state["budget_usd"]="3.25"
        with self.assertRaises(PermissionError):
            require_primary_cost_capacity(policy_reader=reader,health_reader=health)


if __name__=="__main__":
    unittest.main()
