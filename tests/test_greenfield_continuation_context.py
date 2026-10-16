"""Safe semantic scope continuation for greenfield Change Sets.

These tests make no model/provider, GitHub API, Vercel, or database calls.
The worker still validates model writes against the exact returned scopes.
"""
import unittest
from unittest.mock import MagicMock

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.work_unit_context import enforce_write_scopes


FOUNDATION_PATHS=(
    "README.md", "package.json", "tsconfig.json",
    "src/application/organization-service.ts",
    "src/config/server-env.ts",
    "src/domain/organization.ts",
    "src/integrations/identity-provider.ts",
    "src/shared/errors.ts",
    "supabase/migrations/20261015000100_foundation.sql",
)

WAVE_TWO_SCOPES=[
    "database-migrations","auth","authorization","rls-policies","tenant-domain",
]

# Reusable vocabulary exercised by the eight-wave greenfield plan. The
# policy is based on architectural suffixes, never repository/project names.
PLANNED_SCOPE_GROUPS=(
    WAVE_TWO_SCOPES,
    ["audit-domain","attachment-domain","storage-policies","data-lifecycle","database-migrations"],
    ["frontend-app","design-system","authentication-ui","navigation"],
    ["knowledge-domain","knowledge-ui","search","database-migrations"],
    ["ticket-domain","database-migrations","audit-domain","attachment-domain"],
    ["contracts-domain","sla-domain","time-tracking","database-migrations","job-domain"],
    ["ticket-api","ticket-services","authorization","search-and-filters"],
    ["agent-workspace","ticket-ui","queues","saved-views"],
    ["public-api","openapi","webhooks","integration-domain","outbox"],
    ["sla-jobs","automation-domain","notifications","contracts-ui","sla-ui"],
    ["customer-portal","ticket-ui","knowledge-ui","responsive-layouts"],
    ["reporting-domain","dashboards","exports","analytics-queries"],
)


def source(scopes=None,*,project_kind="greenfield",wave=2,explicit=None):
    assignment={
        "scope_keys":list(WAVE_TWO_SCOPES if scopes is None else scopes),
        "required_capabilities":["implementation","migration_authoring"],
        "depends_on":["foundation-app"],
    }
    if explicit is not None:
        assignment["context_paths"]=list(explicit)
    return {
        "project_kind":project_kind,
        "project_key":"product-under-development",
        "repository":"owner/product-under-development",
        "plan_task_key":"tenancy-rbac-rls",
        "agent_key":"development",
        "wave":wave,
        "assignment":assignment,
        "task":{
            "title":"Tenancy, RBAC and RLS",
            "description":None,
            "acceptance_criteria":["Versioned migrations", "Tenant authorization checks"],
        },
    }


def resolved(source_value=None,paths=FOUNDATION_PATHS):
    github=MagicMock()
    github.list_file_paths.return_value=tuple(paths)
    worker=ChangeSetBuilderWorker(
        github=github,store=MagicMock(),producer=MagicMock(),
        impact_engine=MagicMock(),provenance=MagicMock(),
    )
    enriched,context=worker._resolved_repository_context(
        source=source_value if source_value is not None else source(),
        base_commit="verified-candidate-sha",
    )
    github.list_file_paths.assert_called_once_with(ref="verified-candidate-sha")
    return enriched,context


class GreenfieldContinuationScopeTests(unittest.TestCase):
    def test_wave_two_can_create_auth_tenancy_and_versioned_rls(self):
        enriched,context=resolved()
        scopes=enriched["assignment"]["scope_keys"]
        self.assertIn("src/domain/organization.ts",context)
        self.assertIn("supabase/migrations/20261015000100_foundation.sql",context)
        enforce_write_scopes((
            "src/auth/session.ts",
            "src/security/authorization.ts",
            "src/security/permissions.ts",
            "src/domain/tenant.ts",
            "src/persistence/tenancy/memberships.ts",
            "supabase/migrations/20261016000000_tenant_rls.sql",
            "tests/tenant-isolation.test.ts",
        ),scopes)
        self.assertNotIn(".",scopes)
        self.assertNotIn("src/**",scopes)
        for dangerous in (
            ".github/workflows/deploy.yml",".env","secrets/api-key.json",
            "src/billing/write.ts","apps/console/page.tsx",
            "src/auth/../../.github/workflows/deploy.yml",
        ):
            with self.subTest(dangerous=dangerous):
                with self.assertRaises(PermissionError):
                    enforce_write_scopes((dangerous,),scopes)

    def test_remaining_architectural_scope_groups_are_supported(self):
        worker=ChangeSetBuilderWorker(
            github=MagicMock(),store=MagicMock(),producer=MagicMock(),
            impact_engine=MagicMock(),provenance=MagicMock(),
        )
        for group in PLANNED_SCOPE_GROUPS:
            for key in group:
                with self.subTest(key=key):
                    scoped=worker._continuation_semantic_scopes(key,FOUNDATION_PATHS)
                    self.assertTrue(scoped)
                    self.assertNotIn(".",scoped)
                    self.assertNotIn("src/**",scoped)
                    self.assertNotIn(".github/**",scoped)

    def test_unknown_and_unsafe_scopes_fail_closed(self):
        for invalid in ("unrestricted-access","../secrets",".github","billing-admin-root","."):
            with self.subTest(invalid=invalid):
                with self.assertRaises((RuntimeError,PermissionError)):
                    resolved(source([invalid]))

    def test_scope_mapping_requires_authoritative_greenfield_kind(self):
        with self.assertRaisesRegex(RuntimeError,"semantic write scope could not be resolved safely"):
            resolved(source(project_kind="imported"))

    def test_later_wave_requires_real_foundation(self):
        with self.assertRaisesRegex(RuntimeError,"requires an existing"):
            resolved(source(),paths=("README.md",))

    def test_unversioned_migration_root_does_not_grant_sql_writes(self):
        paths=tuple(path for path in FOUNDATION_PATHS
                    if not path.startswith("supabase/migrations/"))
        with self.assertRaisesRegex(RuntimeError,"not safely mapped"):
            resolved(source(),paths=paths)

    def test_explicit_context_does_not_broaden_read_or_write_paths(self):
        enriched,context=resolved(source(explicit=["src/domain/organization.ts"]))
        self.assertEqual(context,("src/domain/organization.ts",))
        scopes=enriched["assignment"]["scope_keys"]
        self.assertNotIn(".",scopes)
        self.assertNotIn("src/**",scopes)
        with self.assertRaises(PermissionError):
            enforce_write_scopes((".github/workflows/unsafe.yml",),scopes)

    def test_new_feature_without_keyword_match_uses_frozen_foundation_context(self):
        limited=("README.md","package.json","tsconfig.json","src/shared/errors.ts",
                 "supabase/migrations/20261015000100_foundation.sql")
        data=source(["billing-api"])
        data["plan_task_key"]="billing-feature"
        data["task"]={"title":"New capability","acceptance_criteria":[]}
        enriched,context=resolved(data,paths=limited)
        self.assertIn("package.json",context)
        self.assertIn("src/shared/errors.ts",context)
        enforce_write_scopes(("src/api/billing/client.ts",),enriched["assignment"]["scope_keys"])
        with self.assertRaises(PermissionError):
            enforce_write_scopes(("src/domain/other.ts",),enriched["assignment"]["scope_keys"])

    def test_scope_policy_is_not_enabled_by_key_alone(self):
        data=source(["billing-api"],project_kind="imported")
        data["task"]={"title":"No related files","acceptance_criteria":[]}
        data["plan_task_key"]="billing-feature"
        limited=("README.md","package.json","tsconfig.json","src/shared/errors.ts")
        with self.assertRaises(RuntimeError):
            resolved(data,paths=limited)


if __name__=="__main__":
    unittest.main()
