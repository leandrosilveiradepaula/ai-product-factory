from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from ai_product_factory.release_policy_store import SupabaseReleasePolicyStore


class Response:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.data).encode()


class ReleasePolicyStoreTests(unittest.TestCase):
    def test_facts_add_latest_passing_product_readiness(self):
        responses=[
            Response({"candidate_commit":"abc","definition_of_done":{},"project_id":"11111111-2222-4333-8444-555555555555"}),
            Response([{
                "status":"passed","baseline_ref":"abc","created_at":"2026-10-07T00:00:00Z",
                "result":{"assessed_commit":"abc","assessment_ref":"audit:1","ready":True,"status":"passed","domains":{},"blockers":[]}
            }]),
            Response([{"project_kind":"platform"}]),
        ]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            out=SupabaseReleasePolicyStore(url="https://x.supabase.co",service_role_key="secret").facts("run-1")
        self.assertTrue(out["product_readiness"]["ready"])
        self.assertEqual(out["product_readiness"]["baseline_ref"],"abc")
        self.assertIn("factory_evaluations?select=",call.call_args_list[1].args[0].full_url)
        self.assertIn("eval_type=eq.product_readiness",call.call_args_list[1].args[0].full_url)
        self.assertEqual(out["project_kind"],"platform")
        self.assertIn("factory_projects?select=project_kind",call.call_args_list[2].args[0].full_url)

    def test_existing_project_reads_independent_baseline_not_json_metadata(self):
        responses=[
            Response({"project_id":"11111111-2222-4333-8444-555555555555"}),
            Response([{"status":"passed","baseline_ref":"a"*40,
                "result":{"ready":True,"project_kind":"platform",
                          "existing_project_baseline":{"status":"passed"}}}]),
            Response([{"project_kind":"existing"}]),
            Response([{"status":"failed","baseline_ref":"a"*40,
                "result":{"ready":True,"coverage":["repository_inventory"]}}]),
        ]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            out=SupabaseReleasePolicyStore(
                url="https://x.supabase.co",service_role_key="secret"
            ).facts("run-1")
        self.assertEqual(out["project_kind"],"existing")
        self.assertEqual(out["existing_project_baseline"]["evaluation_status"],"failed")
        self.assertIn("existing_project_baseline",call.call_args_list[3].args[0].full_url)
        self.assertNotIn("existing_project_baseline",out["product_readiness"]["evaluation_status"])

    def test_missing_project_identity_cannot_be_claimed_from_evaluation_json(self):
        responses=[
            Response({"project_id":None}),
            Response([{"status":"passed","baseline_ref":"a"*40,
                      "result":{"project_kind":"existing","ready":True}}]),
        ]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            out=SupabaseReleasePolicyStore(
                url="https://x.supabase.co",service_role_key="secret"
            ).facts("run-1")
        self.assertNotIn("project_kind",out)
        self.assertEqual(call.call_count,2)


if __name__=="__main__":unittest.main()
