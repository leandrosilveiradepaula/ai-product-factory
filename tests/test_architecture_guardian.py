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


    def test_missing_or_nontext_diff_blocks_security_certificate(self):
        for patch in (None,"","  "):
            with self.subTest(patch=patch):
                out=scan_pull_request_files((
                    {"filename":"src/core.py","status":"modified",
                     "patch":patch,"additions":12,"deletions":3},
                ))
                self.assertIn("unreviewable_diff",{x["code"] for x in out.findings})
                self.assertGreater(out.evidence["blocking_findings"],0)
                self.assertFalse(out.evidence["coverage"]["secret_literals"])
                self.assertFalse(out.evidence["coverage"]["diff_content_available"])
                self.assertEqual(out.evidence["unreviewable_paths"],["src/core.py"])

    def test_binary_and_deleted_unreadable_diff_cannot_pass_as_clean(self):
        for status in ("added","modified","renamed","removed"):
            with self.subTest(status=status):
                out=scan_pull_request_files((
                    {"filename":"assets/image.bin","status":status,
                     "patch":"","additions":0,"deletions":0},
                ))
                self.assertIn("unreviewable_diff",{x["code"] for x in out.findings})
                self.assertEqual(out.evidence["files_reviewed"],1)

    def test_empty_or_unbounded_file_inventory_fails_closed(self):
        out=scan_pull_request_files(())
        self.assertIn("empty_diff_inventory",{x["code"] for x in out.findings})
        self.assertIn("<empty PR>",out.evidence["unreviewable_paths"])
        with self.assertRaisesRegex(RuntimeError,"inventory exceeds"):
            scan_pull_request_files(
                {"filename":f"src/file_{n}.py","status":"modified",
                 "patch":"+changed=True"} for n in range(3001)
            )

    def test_available_safe_diff_retains_explicit_coverage(self):
        out=scan_pull_request_files((
            {"filename":"src/core.py","status":"modified","patch":"+value=1"},
        ))
        self.assertTrue(out.evidence["coverage"]["diff_content_available"])
        self.assertEqual(out.evidence["unreviewable_paths"],[])
        self.assertNotIn("diff_content_available",out.evidence["unknowns"])


if __name__=="__main__":
    unittest.main()
