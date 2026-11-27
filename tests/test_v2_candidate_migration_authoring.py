"""Actual Studio source inventory regression; no model or network calls."""
import unittest
from unittest.mock import MagicMock, patch
from copy import deepcopy

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.work_unit_context import enforce_write_scopes, build_context_packet
from ai_product_factory.reviewed_greenfield_plan import _RECORD

SOURCE = "55e8e8d8422ee044eb1112ab678cb0223e987742"
PATHS = tuple([".github/workflows/validate.yml",".gitignore","README.md","app/README.md","app/editorial-server.test.js","app/editorial.js","app/editorial.test.js","app/server.js","app/server.test.js","docs/PERSISTENCE_RLS_OPERATIONS.md","package-lock.json","package.json","scripts/verify_migration_forward_recovery.sh","src/components/ProjectWorkspace.test.tsx","src/components/StoryboardExportWorkspace.test.tsx","src/components/projects/ProjectWorkspace.tsx","src/components/storyboards/StoryboardExportWorkspace.tsx","src/domain/access-control.test.ts","src/domain/access-control.ts","src/domain/audit.ts","src/domain/contracts.test.ts","src/domain/contracts.ts","src/domain/editorial-pipeline.test.ts","src/domain/project-input.ts","src/domain/prompt-export.test.ts","src/domain/prompts.ts","src/domain/review-recovery.test.ts","src/domain/reviews.ts","src/domain/scene-continuity.test.ts","src/domain/scenes.ts","src/domain/scripts/editorial-pipeline.ts","src/domain/tenancy.ts","src/domain/validation.ts","src/e2e/project-production-flow.test.ts","src/integrations/providers/prompt-providers.ts","src/persistence/audit.ts","src/persistence/supabase-tenancy.test.ts","src/persistence/supabase-tenancy.ts","src/persistence/tenancy.ts","src/security/identity.ts","src/security/rbac.ts","supabase/migrations/20261116132000_tenant_persistence_rls.sql","supabase/tests/bootstrap_auth.sql","supabase/tests/tenant_persistence_rls.sql","tsconfig.json","vitest.config.ts","vitest.setup.ts"])
WORKFLOW = "name: Greenfield candidate validation\non:\n  pull_request:\n  push:\n    branches: [main]\npermissions:\n  contents: read\njobs:\n  candidate:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 15\n    steps:\n      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2\n      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0\n        with:\n          node-version: '22'\n          cache: npm\n      - name: Install from committed, complete lockfile\n        run: npm ci --ignore-scripts --no-audit --no-fund\n      - name: Typecheck source\n        run: npm run typecheck\n      - name: Run unit, UI and end-to-end domain tests\n        run: npm test\n      - name: Validate real HTTP authentication, origin and tenant boundaries\n        run: node --test app/*.test.js\n  tenant-rls-postgres:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 12\n    services:\n      postgres:\n        image: postgres:17.6\n        env:\n          POSTGRES_USER: postgres\n          POSTGRES_PASSWORD: disposable-test-password\n          POSTGRES_DB: studio_disposable\n        ports:\n          - 5432:5432\n        options: >-\n          --health-cmd \"pg_isready -U postgres -d studio_disposable\"\n          --health-interval 5s --health-timeout 5s --health-retries 12\n    env:\n      PGHOST: 127.0.0.1\n      PGPORT: '5432'\n      PGUSER: postgres\n      PGPASSWORD: disposable-test-password\n      PGDATABASE: studio_disposable\n    steps:\n      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2\n      - name: Confirm isolated database endpoint\n        run: |\n          set -euo pipefail\n          test \"$PGHOST\" = 127.0.0.1\n          test \"$PGDATABASE\" = studio_disposable\n          test \"$PGUSER\" = postgres\n          pg_isready -h \"$PGHOST\" -U \"$PGUSER\" -d \"$PGDATABASE\"\n      - name: Create local Supabase Auth contract stub\n        run: psql -X -v ON_ERROR_STOP=1 -f supabase/tests/bootstrap_auth.sql\n      - name: Apply real migration in disposable PostgreSQL\n        run: psql -X -v ON_ERROR_STOP=1 -f supabase/migrations/20261116132000_tenant_persistence_rls.sql\n      - name: Test real RLS, cross-tenant denials and durability\n        run: psql -X -v ON_ERROR_STOP=1 -f supabase/tests/tenant_persistence_rls.sql\n      - name: Prove atomic failure rollback and forward recovery in a second disposable PostgreSQL database\n        run: bash scripts/verify_migration_forward_recovery.sh\n"
MIGRATION = "supabase/migrations/20261126160500_studio_editorial_lifecycle.sql"
OLD = "supabase/migrations/20261116132000_tenant_persistence_rls.sql"


def worker():
    github = MagicMock()
    github.list_file_paths.return_value = PATHS
    github.get_file_text.return_value = WORKFLOW
    return ChangeSetBuilderWorker(github=github, store=MagicMock(), producer=MagicMock(),
                                  impact_engine=MagicMock(), provenance=MagicMock())


def source(task, wave):
    return {"project_kind": "greenfield", "project_key": _RECORD["project_key"],
            "repository": _RECORD["repository"], "journey_id": _RECORD["journey_id"],
            "journey_binding": {"binding_version": 2, "journey_id": _RECORD["journey_id"],
                                "repository": _RECORD["repository"]},
            "wave": wave, "plan_task_key": task["task_key"], "task": task,
            "assignment": {**task, "agent_role": "development"}}


class CandidateMigrationTests(unittest.TestCase):
    @patch("ai_product_factory.change_set_worker.resolve_verified_readonly_imports", return_value=())
    @patch("ai_product_factory.change_set_worker.discover_verified_readonly_callers", return_value=())
    def test_all_four_approved_waves_resolve_on_real_source_inventory(self, *_):
        b = worker()
        for i, task in enumerate(_RECORD["plan"]["tasks"], 1):
            with self.subTest(wave=i):
                original = source(deepcopy(task), i)
                actual, contexts = b._resolved_repository_context(source=original, base_commit=SOURCE)
                expected = set(task["scope_keys"])
                if i == 1:
                    expected.remove(".github/workflows/validate.yml")
                    self.assertIn(OLD, contexts)
                    self.assertIn(".github/workflows/validate.yml", contexts)
                    self.assertIn(OLD, actual["verified_readonly_migration_context_paths"])
                    self.assertIn("Keep .github/workflows/validate.yml unchanged",
                                  " ".join(actual["constraints"]))
                    for blocked in (OLD, ".github/workflows/validate.yml",
                                    "supabase/migrations/20261127100000_other.sql"):
                        with self.assertRaises(PermissionError):
                            enforce_write_scopes([blocked], actual["assignment"]["scope_keys"])
                self.assertEqual(set(actual["assignment"]["scope_keys"]), expected)
                self.assertTrue(set(contexts).issubset(PATHS))
                enforce_write_scopes(expected, actual["assignment"]["scope_keys"])
                self.assertEqual(original["assignment"]["scope_keys"], task["scope_keys"])

    def test_only_exact_new_later_version_with_migration_capability_and_v2_identity(self):
        src=source(deepcopy(_RECORD["plan"]["tasks"][0]),1)
        fn=worker()._new_versioned_migration
        self.assertEqual(fn(MIGRATION, PATHS, src["assignment"], src, SOURCE), OLD)
        for target, paths, caps, binding in (
            ("supabase/migrations/new.sql", PATHS, ["migration_authoring"], src["journey_binding"]),
            ("supabase/migrations/20261116132000_conflict.sql", PATHS, ["migration_authoring"], src["journey_binding"]),
            ("supabase/migrations/20261327100000_invalid.sql", PATHS, ["migration_authoring"], src["journey_binding"]),
            (MIGRATION, tuple(p for p in PATHS if not p.startswith("supabase/migrations/")), ["migration_authoring"], src["journey_binding"]),
            (MIGRATION, PATHS, ["implementation"], src["journey_binding"]),
            (MIGRATION, PATHS, ["migration_authoring"], {}),
            ("supabase/migrations/../20261127100000_escape.sql", PATHS, ["migration_authoring"], src["journey_binding"]),
        ):
            with self.subTest(target=target, caps=caps):
                changed={**src, "journey_binding":binding}
                self.assertIsNone(fn(target,paths,{**src["assignment"],"required_capabilities":caps},changed,SOURCE))

    @patch("ai_product_factory.change_set_worker.resolve_verified_readonly_imports", return_value=())
    @patch("ai_product_factory.change_set_worker.discover_verified_readonly_callers", return_value=())
    def test_no_unverified_ci_path_or_implicit_workflow_permission(self,*_):
        b=worker()
        b.github.get_file_text.return_value="run: echo unverified"
        with self.assertRaisesRegex(PermissionError,"verified existing scoped SQL test"):
            b._resolved_repository_context(source=source(deepcopy(_RECORD["plan"]["tasks"][0]),1),base_commit=SOURCE)

    def test_work_unit_description_and_immutable_request_are_distinct(self):
        src=source(deepcopy(_RECORD["plan"]["tasks"][0]),1)
        src["task"]={**src["task"], "implementation_description":"Scoped wave", "description":"Full request"}
        src["journey_request"]={"text":"Full request","digest":"a"*64}
        packet=build_context_packet(source=src, impact=None, base_commit=SOURCE,
                                    branch="factory/branch").payload
        self.assertEqual(packet["objective"]["description"],"Scoped wave")
        self.assertEqual(packet["journey_request"]["text"],"Full request")
