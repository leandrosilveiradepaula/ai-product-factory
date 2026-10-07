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
            Response({"candidate_commit":"abc","definition_of_done":{}}),
            Response([{
                "status":"passed","baseline_ref":"abc","created_at":"2026-10-07T00:00:00Z",
                "result":{"assessed_commit":"abc","assessment_ref":"audit:1","ready":True,"status":"passed","domains":{},"blockers":[]}
            }]),
        ]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            out=SupabaseReleasePolicyStore(url="https://x.supabase.co",service_role_key="secret").facts("run-1")
        self.assertTrue(out["product_readiness"]["ready"])
        self.assertEqual(out["product_readiness"]["baseline_ref"],"abc")
        self.assertIn("factory_evaluations?select=",call.call_args_list[1].args[0].full_url)
        self.assertIn("eval_type=eq.product_readiness",call.call_args_list[1].args[0].full_url)


if __name__=="__main__":unittest.main()
