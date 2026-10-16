"""Change Set integration retry counter is scoped to the current wave.

Regression was reproduced on the real 8-wave Service Desk Change Set:
three successful integration claims exhausted a lifetime < 3 predicate,
leaving a successfully completed fourth work unit unclaimable.
These offline tests verify the versioned database contract without mutating
the production Control Plane or making model/API calls.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
CURRENT=ROOT/"supabase/migrations/20261016023000_change_set_per_wave_attempts.sql"
BASE=ROOT/"supabase/migrations/20260929033251_factory_change_sets.sql"


def integration_fn(text: str) -> str:
    return text.split(
        "create or replace function public.factory_complete_change_set_integration(",1
    )[1].split("$function$;",1)[0]


class PerWaveIntegrationAttempts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql=CURRENT.read_text()
        cls.fn=integration_fn(cls.sql)
        cls.original=BASE.read_text()

    def test_retry_cap_remains_fail_closed_for_claim_and_recovery(self):
        self.assertIn("and s.attempt_count < 3",self.original)
        self.assertIn("attempt_count>=p_max_attempts",self.original)
        self.assertNotIn("create or replace function public.factory_claim_change_set_integration",self.sql)
        self.assertNotIn("create or replace function public.factory_recover_change_sets",self.sql)

    def test_resets_attempt_count_only_after_advancing_to_next_wave(self):
        self.assertRegex(self.fn,r"if v_next_wave is not null and v_next_wave<=v_set.current_wave")
        final,ongoing=self.fn.split("if v_next_wave is null then",1)[1].split("\n  else\n",1)
        self.assertNotRegex(final,r"attempt_count\s*=\s*0")
        self.assertRegex(ongoing,r"current_wave=v_next_wave,\s*attempt_count=0")
        self.assertIn("if v_set.status<>'integrating'",self.fn)
        self.assertIn("for update",self.fn.lower())
        self.assertIn("v_set.attempt_count<1",self.fn)
        self.assertIn("integration_attempts_by_wave",self.fn)

    def test_preserves_service_role_only_and_invoker_security(self):
        self.assertIn("language plpgsql\nsecurity invoker\nset search_path=''",self.sql)
        self.assertIn("revoke all on function public.factory_complete_change_set_integration",self.sql)
        self.assertIn("from public,anon,authenticated",self.sql)
        self.assertIn("to service_role",self.sql)
        self.assertNotIn("security definer",self.fn.lower())

    def test_repair_is_scoped_and_requires_unchanged_real_incident(self):
        repair=self.sql.split("do $repair$",1)[1]
        for marker in (
            "effc36be-212c-42f2-928b-97381b6d8a28",
            "28497089-9415-43e8-b8e4-06bf754b5607",
            "5c6c4d6c8a23ab1a68c2487dcc32f38aa3d563af",
            "dc044aaaf23f64ca6a3df818430ec1e2a1fa3df5",
            "v_set.attempt_count<>3",
            "v_set.current_wave<>4",
            "v_set.status<>'building'",
            "v_set.lease_owner is not null",
            "v_set.lease_expires_at is not null",
            "v_prior_units<>4 or v_prior_waves<>3",
            "v_current_units<>1",
            "v_later_changed<>0",
            "change_set.integration.attempt_counter_rebased",
            "operator-applied-versioned-migration",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,repair)
        self.assertIn("if not found then return; end if;",repair)
        self.assertIn("if v_set.current_wave>4",repair)
        self.assertIn("if not found then",repair)
        self.assertIn("min(task_id::text)::uuid",repair)
        self.assertNotIn("max(task_id)",repair)

    def test_repair_has_no_runtime_automerge_or_silent_production_rollout(self):
        self.assertNotIn("merge_pull_request(",self.sql)
        self.assertNotIn("factory-wake",self.sql)
        self.assertNotIn("grant execute",self.sql.split("do $repair$",1)[1].lower())


if __name__=="__main__":
    unittest.main()
