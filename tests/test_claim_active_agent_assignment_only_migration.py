from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261006152500_claim_active_agent_assignment_only.sql"


class ClaimActiveAgentAssignmentOnlyMigrationTests(unittest.TestCase):
    def test_direct_and_codex_select_exact_active_assignment(self):
        text=MIGRATION.read_text()
        self.assertGreaterEqual(text.count("select ra.id,a2.agent_key into v_assignment_id,v_agent_key"),2)
        self.assertGreaterEqual(text.count("where ra.run_id=v_run.id and ra.status in ('assigned','claimed')"),2)
        self.assertGreaterEqual(text.count("order by ra.assigned_at desc,ra.id desc"),2)

    def test_claim_updates_only_selected_assignment(self):
        text=MIGRATION.read_text()
        self.assertGreaterEqual(
            text.count("where id=v_assignment_id\n    and status in ('assigned','claimed')"),
            2,
        )
        self.assertNotIn(
            "update public.factory_run_agent_assignments set status='claimed',claimed_at=coalesce(claimed_at,now()) where run_id=v_run.id",
            text,
        )

    def test_historical_blocked_assignments_are_not_reactivated(self):
        text=MIGRATION.read_text()
        self.assertNotIn("status in ('assigned','claimed','blocked')",text)
        self.assertIn("'assignment_id',v_assignment_id",text)

    def test_internal_claim_rpcs_remain_service_role_only(self):
        text=MIGRATION.read_text()
        self.assertIn("revoke all on function public.factory_claim_next_agent_direct_run(text,text,uuid)",text)
        self.assertIn("grant execute on function public.factory_claim_next_agent_direct_run(text,text,uuid)",text)
        self.assertIn("revoke all on function public.factory_claim_next_agent_codex_run(text,text,uuid)",text)
        self.assertIn("grant execute on function public.factory_claim_next_agent_codex_run(text,text,uuid)",text)


if __name__=="__main__":
    unittest.main()
