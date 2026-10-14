"""Authoritative queue signals replace bounded samples for dispatcher liveness."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261013235000_scheduler_queue_signals.sql").read_text()
PY=(ROOT/"src/ai_product_factory/schedule_probe.py").read_text()

class SchedulerExistenceContract(unittest.TestCase):
    def test_exists_query_has_active_project_and_execution_route_guards(self):
        self.assertEqual(SQL.count("create or replace function"),1)
        self.assertEqual(SQL.count("exists("),3)
        self.assertIn("p.is_active=true",SQL)
        self.assertIn("t.status='queued_execution'",SQL)
        self.assertIn("r.execution_route in ('direct','codex')",SQL)
        self.assertIn("r.status='awaiting_codex_manual'",SQL)
        self.assertIn("security invoker",SQL)
        self.assertIn("from public,anon,authenticated",SQL)
        self.assertIn("to service_role",SQL)
        self.assertNotIn("insert into",SQL.lower())
        self.assertNotIn("update public.",SQL.lower())

    def test_python_fails_closed_if_rpc_unavailable(self):
        self.assertIn("authoritative queue signal unavailable",PY)
        self.assertIn("invalid authoritative queue signal response",PY)
        self.assertIn("type(payload.get(k)) is not bool",PY)
        self.assertIn("signals = self._execution_signals()",PY)
        self.assertIn('assigned_execution_work = signals["routed_execution_work"]',PY)
        self.assertIn('product_work = signals["product_work"]',PY)
        self.assertIn('codex_manual_work = signals["codex_manual_work"]',PY)

if __name__=="__main__":
    unittest.main()
