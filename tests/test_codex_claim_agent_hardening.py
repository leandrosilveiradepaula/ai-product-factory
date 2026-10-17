"""Offline fail-closed contracts for Codex agent claim hardening (no DB writes)."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_product_factory.agent_scheduler import SupabaseAgentScheduler
from ai_product_factory.codex_run_queue import SupabaseCodexRunQueue

SQL = (Path(__file__).resolve().parents[1] / "supabase/migrations/20261014032600_codex_claim_agent_hardening.sql").read_text()


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class CodexSQLContracts(unittest.TestCase):
    def test_required_functions_are_terminated(self):
        self.assertEqual(SQL.count("CREATE OR REPLACE FUNCTION"), 3)
        self.assertEqual(SQL.count("$function$;"), 3)
        self.assertIn("for update of r skip locked", SQL.lower())
        self.assertIn("for update of ra skip locked", SQL.lower())

    def test_scheduler_preserves_selected_agent_and_tools(self):
        self.assertIn("a.allowed_tools ?& array['codex','github_write']", SQL)
        self.assertIn("v_assignment->>'agent_key' is distinct from v_codex_agent_key", SQL)
        self.assertIn("Codex allocator changed selected agent or required tools", SQL)

    def test_claim_filters_tools_capabilities_and_exact_agent(self):
        self.assertEqual(SQL.count("a2.allowed_tools ?& array['codex','github_write']"), 2)
        self.assertEqual(SQL.count("(p_agent_key is null or a2.agent_key=p_agent_key)"), 2)
        self.assertIn("coalesce(t.required_capabilities,'[]'::jsonb)", SQL)
        self.assertIn("run_id=v_run.id", SQL)
        self.assertIn("automatic Codex assignment update lost", SQL)
        self.assertIn("proj.is_active=true", SQL)
        self.assertIn("metadata->>'codex_execution_mode'='automatic'", SQL)

    def test_matrix_and_access_remain_fail_closed(self):
        self.assertIn("a.allowed_tools ?& array['codex','github_write']", SQL)
        self.assertIn("and a.is_active", SQL)
        for name, args in (
            ("factory_claim_next_agent_codex_run", "text,text,uuid"),
            ("factory_schedule_eligible_codex_run", "uuid,text"),
            ("factory_agent_work_matrix", "integer"),
        ):
            self.assertIn(f"revoke all on function public.{name}({args}) from public,anon,authenticated;", SQL)
            self.assertIn(f"grant execute on function public.{name}({args}) to service_role;", SQL)


class CodexClientContracts(unittest.TestCase):
    @staticmethod
    def _assignment(**overrides):
        payload = dict(assignment_id="a", agent_id="b", agent_key="codex-dev",
                       role="development", max_concurrency=1, model_policy={},
                       allowed_tools=["github_write", "codex"], run_id="run-one", task_id="task")
        payload.update(overrides)
        return payload

    @staticmethod
    def _claimed(**overrides):
        payload = dict(run_id="run-one", project_id="project-uuid", execution_generation=1, task_id="task", project_key="p", repository="owner/repo",
                       title="Implement", description="", branch="factory/cs-x/t",
                       codex_level=1, agent_key="codex-dev")
        payload.update(overrides)
        return payload

    def test_schedule_rejects_incompatible_tools(self):
        client = SupabaseAgentScheduler(url="https://example.supabase.co", service_role_key="test")
        with patch.object(client, "_rpc", return_value=self._assignment(allowed_tools=["codex"])):
            with self.assertRaisesRegex(RuntimeError, "required route tools"):
                client.schedule_eligible_codex(run_id="run-one")

    def test_schedule_rejects_wrong_run(self):
        client = SupabaseAgentScheduler(url="https://example.supabase.co", service_role_key="test")
        with patch.object(client, "_rpc", return_value=self._assignment(run_id="another")):
            with self.assertRaisesRegex(RuntimeError, "inconsistent run ID"):
                client.schedule_eligible_codex(run_id="run-one")

    def test_schedule_accepts_exact_capable_agent(self):
        client = SupabaseAgentScheduler(url="https://example.supabase.co", service_role_key="test")
        with patch.object(client, "_rpc", return_value=self._assignment()):
            self.assertEqual(client.schedule_eligible_codex(run_id="run-one").agent_key, "codex-dev")

    def test_claim_rejects_mismatched_agent(self):
        client = SupabaseCodexRunQueue(url="https://example.supabase.co", service_role_key="test")
        with patch("urllib.request.urlopen", return_value=Response(self._claimed(agent_key="other"))):
            with self.assertRaisesRegex(RuntimeError, "different assigned agent"):
                client.claim_next("worker", agent_key="codex-dev", run_id="run-one")

    def test_claim_rejects_mismatched_run(self):
        client = SupabaseCodexRunQueue(url="https://example.supabase.co", service_role_key="test")
        with patch("urllib.request.urlopen", return_value=Response(self._claimed(run_id="another"))):
            with self.assertRaisesRegex(RuntimeError, "different run ID"):
                client.claim_next("worker", agent_key="codex-dev", run_id="run-one")

    def test_claim_accepts_exact_agent_and_run(self):
        client = SupabaseCodexRunQueue(url="https://example.supabase.co", service_role_key="test")
        with patch("urllib.request.urlopen", return_value=Response(self._claimed())) as call:
            claimed = client.claim_next("worker", agent_key="codex-dev", run_id="run-one")
        self.assertEqual(claimed.run_id, "run-one")
        self.assertEqual(json.loads(call.call_args.args[0].data)["p_agent_key"], "codex-dev")


if __name__ == "__main__":
    unittest.main()
