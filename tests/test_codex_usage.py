import json
import unittest
from unittest.mock import patch

from ai_product_factory.codex_usage import SupabaseCodexUsageRecorder


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.data).encode()


class CodexUsageTests(unittest.TestCase):
    def test_records_invocation_through_durable_rpc(self):
        with patch(
            "urllib.request.urlopen",
            return_value=Response({"run_id": "r", "invocation_count": 1}),
        ) as call:
            out = SupabaseCodexUsageRecorder(
                url="https://x.supabase.co", service_role_key="secret"
            ).record_invocation(run_id="r")
        self.assertEqual(out["invocation_count"], 1)
        request = call.call_args.args[0]
        self.assertTrue(
            request.full_url.endswith("/rest/v1/rpc/factory_record_codex_invocation")
        )
        body = json.loads(request.data.decode())
        self.assertEqual(body["p_run_id"], "r")
        self.assertEqual(body["p_reported_usage"]["status"], "started")


if __name__ == "__main__":
    unittest.main()
