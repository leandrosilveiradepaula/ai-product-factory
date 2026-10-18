import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261018003000_fence_change_set_integration_epoch.sql").read_text()


class IntegrationEpochMigrationTests(unittest.TestCase):
    def test_checkpoint_requires_project_generation_worker_lease_and_wave(self):
        definition=SQL.split("create or replace function public.factory_assert_change_set_integration_epoch(",1)[1].split("$f$;",1)[0]
        for token in (
            "p_project_id uuid","p_generation bigint","p_worker_id text","p_wave integer",
            "v_state is distinct from 'running'","v_generation is distinct from p_generation",
            "v_set.status is distinct from 'integrating'",
            "v_set.current_wave is distinct from p_wave",
            "v_set.lease_owner is distinct from p_worker_id",
            "v_set.lease_expires_at<=now()",
            "v_set.project_id is distinct from p_project_id",
        ):
            with self.subTest(token=token):
                self.assertIn(token,definition)

    def test_claim_filters_stopped_projects_and_returns_epoch(self):
        claim=SQL.split("create or replace function public.factory_claim_change_set_integration(",1)[1]
        for token in ("c.state='running'","c.generation>0","for update of s skip locked",
                      "'project_id',v_set.project_id","'execution_generation',v_generation",
                      "'lease_owner',p_worker_id","p_lease_seconds>600"):
            with self.subTest(token=token):
                self.assertIn(token,claim)

    def test_checkpoint_and_claim_are_service_role_only(self):
        for function in ("factory_assert_change_set_integration_epoch(uuid,uuid,bigint,text,integer)",
                         "factory_claim_change_set_integration(text,integer)"):
            self.assertIn("revoke all on function public."+function+" from public,anon,authenticated",SQL)
            self.assertIn("grant execute on function public."+function+" to service_role",SQL)


if __name__=="__main__":
    unittest.main()
