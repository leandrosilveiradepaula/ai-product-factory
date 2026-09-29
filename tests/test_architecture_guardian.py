import unittest

from ai_product_factory.architecture_guardian import scan_pull_request_files


class ArchitectureGuardianTests(unittest.TestCase):
    def test_blocks_literal_secret_and_client_secret_boundary(self):
        out=scan_pull_request_files((
            {"filename":"apps/console/app/page.tsx","status":"modified","patch":"+ const x='sk-proj-abcdefghijklmnop';\n+ const y=process.env.NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY;"},
        ))
        codes={x["code"] for x in out.findings}
        self.assertIn("openai_key",codes)
        self.assertIn("client_service_role",codes)
        self.assertGreaterEqual(out.evidence["blocking_findings"],2)

    def test_blocks_unsafe_workflow_and_sql_rls_changes(self):
        out=scan_pull_request_files((
            {"filename":".github/workflows/bad.yml","status":"modified","patch":"+pull_request_target:\n+permissions: write-all\n+run: codex --sandbox danger-full-access"},
            {"filename":"supabase/migrations/x.sql","status":"added","patch":"+alter table public.x disable row level security;\n+grant select on public.x to anon;"},
        ))
        codes={x["code"] for x in out.findings}
        self.assertTrue({"pull_request_target","write_all_permissions","danger_full_access","disable_rls","permissive_public_grant"}.issubset(codes))

    def test_database_lineage_is_factual_and_destructive_change_is_warning(self):
        out=scan_pull_request_files((
            {"filename":"supabase/migrations/x.sql","status":"added","patch":"+alter table public.orders drop column legacy;\n+create view public.order_summary as select * from public.orders;"},
        ))
        self.assertIn("destructive_schema_change",{x["code"] for x in out.findings})
        lineage=out.evidence["database_lineage"][0]
        self.assertTrue(any(x["name"]=="orders" for x in lineage["objects"]))
        self.assertIn("orders",lineage["references"])

    def test_api_and_dependency_changes_require_evidence_without_fake_scan_claims(self):
        out=scan_pull_request_files((
            {"filename":"apps/console/app/api/customers/route.ts","status":"modified","patch":"+export async function GET(){}"},
            {"filename":"package-lock.json","status":"modified","patch":"+  \"new-lib\": \"1.0.0\""},
        ))
        codes={x["code"] for x in out.findings}
        self.assertIn("api_contract_surface_changed",codes)
        self.assertIn("dependency_surface_changed",codes)
        self.assertFalse(out.evidence["coverage"]["dependency_vulnerability_scan"])
        self.assertFalse(out.evidence["coverage"]["full_sast"])
        self.assertIn("sbom_generation",out.evidence["unknowns"])
        self.assertEqual(out.evidence["blocking_findings"],0)

    def test_safe_patch_passes_without_model(self):
        out=scan_pull_request_files((
            {"filename":"src/core.py","status":"modified","patch":"+value=1"},
        ))
        self.assertEqual(out.findings,())
        self.assertFalse(out.evidence["model_call"])
        self.assertEqual(out.evidence["scanner"],"architecture_guardian_v1")


if __name__=="__main__":
    unittest.main()
