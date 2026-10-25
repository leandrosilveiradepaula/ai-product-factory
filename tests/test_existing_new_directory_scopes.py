"""Exact new directories in populated repositories stay narrow and auditable."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.work_unit_context import build_context_packet, enforce_write_scopes


FILES = (
    "AGENTS.md",
    "docs/codex/CURRENT_TASK.md",
    "src/components/layout/Sidebar.tsx",
    "src/app/(dashboard)/layout.tsx",
    "src/app/(dashboard)/reports/page.tsx",
    "src/lib/session.ts",
    "src/lib/sidebar-navigation.test.ts",
    "src/app/api/gemini/specs/route.ts",
)
NEW = (
    "src/app/(dashboard)/service-desk/page.tsx",
    "src/lib/service-desk/entry-guard.ts",
    "src/lib/service-desk/entry-guard.test.ts",
)
ALLOWED = (
    "src/components/layout/Sidebar.tsx",
    *NEW,
    "docs/codex/CURRENT_TASK.md",
)


def builder():
    github = MagicMock()
    github.list_file_paths.return_value = FILES
    return ChangeSetBuilderWorker(
        github=github, store=MagicMock(), producer=MagicMock(),
        impact_engine=MagicMock(), provenance=MagicMock(),
    )


def scoped_source(scopes=ALLOWED):
    return {
        "project_kind": "existing",
        "project_key": "crm-infodive",
        "repository": "owner/crm",
        "wave": 1,
        "plan_task_key": "service-desk-entry",
        "task": {"title": "Implementar entrada protegida Service Desk"},
        "assignment": {
            "scope_keys": list(scopes),
            "context_paths": [
                "AGENTS.md",
                "docs/codex/CURRENT_TASK.md",
                "src/components/layout/Sidebar.tsx",
            ],
        },
    }


class ExactNewDirectoryScopesTests(unittest.TestCase):
    def test_one_new_directory_allows_only_explicit_new_files(self):
        worker = builder()
        for path in NEW:
            with self.subTest(path=path):
                self.assertEqual(worker._bounded_file_scope(path, FILES), (path, None))

        source, inspected = worker._resolved_repository_context(
            source=scoped_source(), base_commit="a" * 40,
        )
        self.assertEqual(tuple(source["assignment"]["scope_keys"]), ALLOWED)
        self.assertEqual(inspected, tuple(source["assignment"]["context_paths"]))
        packet = build_context_packet(
            source=source, impact=None, base_commit="a" * 40,
            branch="factory/change-set-123", repository_snapshot={
                "AGENTS.md": "Agent governance",
                "docs/codex/CURRENT_TASK.md": "Authorized files",
                "src/components/layout/Sidebar.tsx": "Existing sidebar",
            },
        )
        self.assertEqual(tuple(packet.payload["repository"]["write_scopes"]), ALLOWED)
        enforce_write_scopes(NEW, packet.payload["repository"]["write_scopes"])
        with self.assertRaises(PermissionError):
            enforce_write_scopes(
                ["src/app/api/gemini/specs/route.ts"],
                packet.payload["repository"]["write_scopes"],
            )

    def test_one_new_directory_requires_populated_immediate_ancestor(self):
        worker = builder()
        for path in (
            "src/nonexistent/mystery.ts",
            "src/never-before/nested/file.ts",
            "src/lib/never-before/deeper/file.ts",
            "src/app/(dashboard)/new/child/page.tsx",
            "src/lib/.secrets/credentials.ts",
            "src/../../escape/file.ts",
            "supabase/migrations/new.sql",
            ".github/workflows/unsafe.yml",
        ):
            with self.subTest(path=path):
                self.assertIsNone(worker._bounded_file_scope(path, FILES))

    def test_unverified_exact_file_must_block_not_map_to_existing_context(self):
        worker = builder()
        unsafe = "src/lib/new/deeper/entry-guard.ts"
        with self.assertRaisesRegex(PermissionError, "exact new-file scope"):
            worker._resolved_repository_context(
                source=scoped_source(["src/components/layout/Sidebar.tsx", unsafe]),
                base_commit="a" * 40,
            )

    def test_existing_file_and_literal_conditional_remain_supported(self):
        worker = builder()
        self.assertEqual(
            worker._bounded_file_scope("src/components/layout/Sidebar.tsx", FILES),
            ("src/components/layout/Sidebar.tsx", None),
        )
        self.assertEqual(
            worker._bounded_file_scope(
                "src/lib/service-desk/entry-guard.ts if needed", FILES
            ),
            ("src/lib/service-desk/entry-guard.ts", "if needed"),
        )

    def test_semantic_scope_does_not_gain_exact_new_directory_exception(self):
        worker = builder()
        with self.assertRaises(PermissionError):
            worker._resolved_repository_context(
                source=scoped_source(["src/never-before/nested/file.ts"]),
                base_commit="a" * 40,
            )


if __name__ == "__main__":
    unittest.main()
