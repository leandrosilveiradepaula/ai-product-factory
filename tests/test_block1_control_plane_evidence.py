"""Contract tests for independent read-only Block 1 database evidence."""
from pathlib import Path
import unittest

SQL = Path(__file__).resolve().parents[1] / "scripts" / "audit_block1_control_plane.sql"

class ControlPlaneEvidenceContract(unittest.TestCase):
    def test_read_only_transaction_and_no_ddl_dml(self):
        import re
        source = SQL.read_text(encoding="utf-8")
        statements = re.sub(r"--[^\n]*", "", source)
        self.assertIn("BEGIN TRANSACTION READ ONLY;", statements)
        self.assertIn("COMMIT;", statements)
        for forbidden in ("ALTER", "CREATE", "DROP", "GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "EXECUTE", "CALL", "SET ROLE"):
            # Ignore SQL string literals used as privilege names and policy names.
            cleaned = re.sub(r"'(?:''|[^'])*'", "''", statements)
            self.assertNotRegex(cleaned, rf"(?i)\b{forbidden}\b")

    def test_required_catalog_fences_and_no_false_certification(self):
        sql = SQL.read_text(encoding="utf-8")
        for marker in ("pg_class", "pg_policies", "pg_proc", "has_table_privilege",
                       "has_function_privilege", "relrowsecurity", "prosecdef",
                       "public_write_grants", "public_or_write_policies",
                       "publicly_executable_security_definers",
                       "false AS adversarial_rls_certified", "false AS product_ready"):
            self.assertIn(marker, sql)

if __name__ == "__main__":
    unittest.main()
