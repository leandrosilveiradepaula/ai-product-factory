from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261030110000_product_readiness_certification.sql").read_text().lower()

class MigrationContractTests(unittest.TestCase):
 def test_certification_migration_is_service_only_and_idempotent(self):
    self.assertIn("factory_product_readiness_certifications",SQL)
    self.assertIn("unique(project_id, assessed_commit, evidence_digest)",SQL)
    self.assertIn("for update",SQL)
    self.assertIn("factory_begin_product_readiness_certification_v1",SQL)
    self.assertIn("factory_persist_product_readiness_certification_v1",SQL)
    self.assertIn("revoke all on function",SQL); self.assertIn("to service_role",SQL)
    self.assertIn("grant execute",SQL); self.assertNotIn("to anon",SQL)

 def test_certification_does_not_change_observer_or_release_authority(self):
    self.assertNotIn("workflow",SQL)
    self.assertNotIn("factory_finalize_console_human_release",SQL)
    self.assertNotIn("factory_enqueue",SQL)
