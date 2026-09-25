import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "schemas" / "supabase" / "001_control_plane.sql").read_text(encoding="utf-8").lower()


class ControlPlaneSchemaSecurityTests(unittest.TestCase):
    def test_control_plane_tables_enable_rls(self):
        self.assertIn("enable row level security", SCHEMA)
        self.assertIn("factory_projects", SCHEMA)
        self.assertIn("factory_audit_events", SCHEMA)

    def test_client_roles_are_revoked_and_service_role_is_granted(self):
        self.assertIn("revoke all on table public.%i from anon, authenticated", SCHEMA)
        self.assertIn("grant all on table public.%i to service_role", SCHEMA)


if __name__ == "__main__":
    unittest.main()
