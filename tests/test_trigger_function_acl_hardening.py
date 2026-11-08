"""Static ACL contract for internal Factory trigger functions."""
from pathlib import Path
import unittest


SQL = (Path(__file__).resolve().parents[1] /
       "supabase/migrations/20261108011146_harden_trigger_function_acls.sql"
       ).read_text(encoding="utf-8").lower()

FUNCTIONS = (
    "factory_propagate_journey_binding_v2",
    "factory_stamp_ci_release_epoch",
    "factory_sync_ci_repair_lease",
    "factory_sync_ci_repair_request",
)


class TriggerFunctionAclHardeningTests(unittest.TestCase):
    def test_internal_trigger_functions_are_not_public_rpcs(self):
        for function in FUNCTIONS:
            with self.subTest(function=function):
                self.assertIn(
                    f"revoke all on function public.{function}()\n"
                    "  from public, anon, authenticated;",
                    SQL,
                )
                self.assertIn(
                    f"grant execute on function public.{function}()\n"
                    "  to service_role;",
                    SQL,
                )

    def test_migration_cannot_expand_anonymous_or_authenticated_access(self):
        self.assertNotIn("to anon", SQL)
        self.assertNotIn("to authenticated", SQL)
        self.assertNotIn("security definer", SQL)


if __name__ == "__main__":
    unittest.main()
