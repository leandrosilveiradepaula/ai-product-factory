"""Offline contract: exhaustive downstream SQL scheduler wake signals."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261014001500_extend_scheduler_queue_signals.sql").read_text()
SOURCE=(ROOT/"src/ai_product_factory/schedule_probe.py").read_text()

class DownstreamWakeContract(unittest.TestCase):
    def test_sql_has_exact_bounded_permissions_and_no_mutation(self):
        names=("product_work","routed_execution_work","codex_manual_work",
               "integration_work","ci_work","release_work",
               "specialist_security_work","specialist_qa_work","specialist_operations_work")
        self.assertEqual(SQL.count("create or replace function"),1)
        self.assertEqual(SQL.count("exists("),9)
        for name in names:self.assertEqual(SQL.count("'"+name+"'"),1)
        for marker in ("language sql stable security invoker","from public,anon,authenticated;",
                       "to service_role;","cs.status in ('building','integrating')",
                       "r.status='ci_pending'","r.status='awaiting_release'",
                       "j.status='queued' and j.role='security'"):
            self.assertIn(marker,SQL)
        for bad in ("insert into","update public.","delete from","truncate table"):
            self.assertNotIn(bad,SQL.lower())

    def test_python_uses_authoritative_signals_and_preserves_preview_policy(self):
        for marker in ('signals["integration_work"]','signals["ci_work"]',
                       'signals["release_work"]','signals[f"specialist_{role}_work"]',
                       "is_delivery_preview_run(run)","is_quota_blocked_candidate(run,blocks)",
                       "pending_change_set_work and bool(portfolio_candidates)"):
            self.assertIn(marker,SOURCE)
        self.assertIn("invalid authoritative queue signal response",SOURCE)

if __name__=="__main__":
    unittest.main()
