import json
import unittest
from unittest.mock import patch

from ai_product_factory.codex_run_queue import SupabaseCodexRunQueue


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.data).encode() if self.data is not None else b""


class CodexRunQueueTests(unittest.TestCase):
    def test_claim_maps_codex_item(self):
        payload = {
            "run_id": "r",
            "task_id": "t",
            "project_key": "p",
            "repository": "owner/repo",
            "issue_number": None,
            "title": "Implement",
            "description": "Task",
            "branch": "factory/task-t",
            "codex_level": 2,
            "human_gate_required": False,
        }
        with patch("urllib.request.urlopen", return_value=Response(payload)) as call:
            item = SupabaseCodexRunQueue(
                url="https://x.supabase.co", service_role_key="secret"
            ).claim_next("worker")
        self.assertEqual(item.repository, "owner/repo")
        self.assertEqual(item.codex_level, 2)
        self.assertIsNone(item.issue_number)
        request = call.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/rest/v1/rpc/factory_claim_next_agent_codex_run"))
        self.assertNotIn(b"secret", request.data)

    def test_empty_queue(self):
        with patch("urllib.request.urlopen", return_value=Response(None)):
            item = SupabaseCodexRunQueue(
                url="https://x.supabase.co", service_role_key="secret"
            ).claim_next("worker")
        self.assertIsNone(item)


if __name__ == "__main__":
    unittest.main()
