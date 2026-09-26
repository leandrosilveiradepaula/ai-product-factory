import json
import unittest
from unittest.mock import patch

from ai_product_factory.codex_usage_store import SupabaseCodexUsageStore


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return b"" if self.data is None else json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_requires_existing_routing_ledger_entry(self):
        with patch("urllib.request.urlopen",return_value=Response([])):
            with self.assertRaises(RuntimeError):
                SupabaseCodexUsageStore(url="https://x.supabase.co",secret_key="sb_secret_x").require_entry("r")

    def test_records_one_invocation_without_inventing_cost(self):
        responses=[
            Response([{"id":3,"invocation_count":0,"reported_usage":{"route":"codex"}}]),
            Response([{"id":3,"invocation_count":1}]),
        ]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            SupabaseCodexUsageStore(url="https://x.supabase.co",secret_key="sb_secret_x").record_invocation(
                "r",status="success",trace_events=8
            )
        body=json.loads(call.call_args_list[1].args[0].data.decode())
        self.assertEqual(body["invocation_count"],1)
        self.assertEqual(body["reported_usage"]["last_status"],"success")
        self.assertIsNone(body["reported_usage"]["cost_usd"])


if __name__=="__main__":unittest.main()
