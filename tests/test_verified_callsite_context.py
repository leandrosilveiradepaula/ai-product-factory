import unittest
from unittest.mock import Mock

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.verified_callsite_context import discover_verified_readonly_callers


SHA = "a" * 40
PATHS = (
    "AGENTS.md", "docs/codex/CURRENT_TASK.md",
    "src/services/ContractService.ts", "src/services/ContractService.test.ts",
    "src/app/(dashboard)/contracts/actions.ts",
    "src/app/(dashboard)/contracts/page.tsx",
    "src/hooks/useContracts.ts",
    "src/types/contract.ts", "src/types/deal.ts",
    "src/lib/auth-server.ts", "src/lib/server-authorization.ts",
    "src/lib/permission-matrix.ts", "src/services/DealService.ts",
    "src/components/Other.tsx",
)
SOURCE = {
    "plan_task_key": "issue209-contracts-isolated-read",
    "task": {"title": "Contract isolation", "acceptance_criteria": [
        "Inspect real getContracts callers, the contract/deal types, server-side RBAC and authorization before changing the query."
    ]},
    "assignment": {
        "context_paths": ["src/services/ContractService.ts"],
        "scope_keys": ["src/services/ContractService.ts", "src/services/ContractService.test.ts", "contract-query-call-sites"],
    },
}
FILES = {
    "AGENTS.md": "No production merge",
    "docs/codex/CURRENT_TASK.md": "Issue scope read-only callers",
    "src/services/ContractService.ts":
        "export class ContractService { static async getContracts(organizationId: string) {} }",
    "src/services/ContractService.test.ts": "export const contractScopeTest = true;",
    "src/app/(dashboard)/contracts/actions.ts":
        "import { ContractService } from '@/services/ContractService'; "
        "export async function getContracts() { return ContractService.getContracts('org'); }",
    "src/app/(dashboard)/contracts/page.tsx":
        "import { getContracts } from './actions'; export default async function ContractsPage() { return getContracts(); }",
    "src/hooks/useContracts.ts":
        "import { getContracts } from '@/app/(dashboard)/contracts/actions'; export function useContracts() { return getContracts(); }",
    "src/types/contract.ts": "export type Contract = { dealId?: string };",
    "src/types/deal.ts": "export type Deal = { owner_id?: string };",
    "src/lib/auth-server.ts": "export function requireSessionContext() {}",
    "src/lib/server-authorization.ts": "export function requirePermission() {}",
    "src/lib/permission-matrix.ts": "export const ROLE_PERMISSIONS = {};",
    "src/services/DealService.ts": "export class DealService {}",
    "src/components/Other.tsx": "export function Other() {}",
}


class VerifiedCallsiteContextTests(unittest.TestCase):
    def worker(self, files=None):
        files = files or FILES
        github = Mock()
        github.list_file_paths.return_value = PATHS
        github.get_file_text.side_effect = lambda path, ref: files[path]
        worker = object.__new__(ChangeSetBuilderWorker)
        worker.github = github
        return worker

    def test_actual_callsite_and_trust_sources_are_readonly(self):
        worker = self.worker()
        result, context = worker._resolved_repository_context(
            source=SOURCE, base_commit=SHA
        )
        readonly = result["verified_readonly_callsite_paths"]
        self.assertIn("src/app/(dashboard)/contracts/actions.ts", readonly)
        self.assertIn("src/types/contract.ts", readonly)
        self.assertIn("src/lib/auth-server.ts", readonly)
        self.assertIn("src/lib/server-authorization.ts", readonly)
        self.assertIn("src/lib/permission-matrix.ts", readonly)
        self.assertNotIn("src/components/Other.tsx", readonly)
        self.assertLessEqual(len(context), 12)
        self.assertTrue(set(readonly).issubset(context))
        self.assertNotIn("src/app/(dashboard)/contracts/actions.ts", result["assignment"]["scope_keys"])
        packet, unsafe = worker._repository_snapshot_with_safety(
            source=result, base_commit=SHA
        )
        self.assertTrue(set(readonly).issubset(packet))
        self.assertNotIn("src/app/(dashboard)/contracts/actions.ts", unsafe)
        for call in worker.github.get_file_text.call_args_list:
            self.assertEqual(call.kwargs["ref"], SHA)

    def test_approved_exact_server_action_becomes_writable_not_readonly(self):
        """Only an exact plan scope can make a verified callsite writable."""
        worker = self.worker()
        source = {**SOURCE, "assignment": {
            **SOURCE["assignment"],
            "scope_keys": [
                *SOURCE["assignment"]["scope_keys"],
                "src/app/(dashboard)/contracts/actions.ts",
            ],
        }}
        result, context = worker._resolved_repository_context(source=source, base_commit=SHA)
        action = "src/app/(dashboard)/contracts/actions.ts"
        self.assertIn(action, context)
        self.assertIn(action, result["assignment"]["scope_keys"])
        self.assertNotIn(action, result["verified_readonly_callsite_paths"])
        self.assertIn("src/types/contract.ts", result["verified_readonly_callsite_paths"])
        packet, unsafe = worker._repository_snapshot_with_safety(source=result, base_commit=SHA)
        self.assertEqual(packet[action], FILES[action])
        self.assertNotIn(action, unsafe)
        self.assertNotIn("src/lib/auth-server.ts", result["assignment"]["scope_keys"])
        self.assertNotIn("src/app/(dashboard)/contracts/page.tsx", result["assignment"]["scope_keys"])
        for call in worker.github.get_file_text.call_args_list:
            self.assertEqual(call.kwargs["ref"], SHA)

    def test_missing_verified_server_callsite_blocks_before_producer(self):
        files = dict(FILES)
        files["src/app/(dashboard)/contracts/actions.ts"] = "export function noop() {}"
        files["src/app/(dashboard)/contracts/page.tsx"] = "export function noop() {}"
        files["src/hooks/useContracts.ts"] = "export function noop() {}"
        worker = self.worker(files)
        with self.assertRaisesRegex(PermissionError, "call-site and server action evidence missing"):
            worker._resolved_repository_context(source=SOURCE, base_commit=SHA)

    def test_not_triggered_for_unrelated_scopes(self):
        worker = self.worker()
        source = dict(SOURCE)
        assignment = dict(SOURCE["assignment"])
        assignment["scope_keys"] = ["src/services/ContractService.ts"]
        source["assignment"] = assignment
        result, context = worker._resolved_repository_context(
            source=source, base_commit=SHA
        )
        self.assertEqual(result["verified_readonly_callsite_paths"], [])
        self.assertNotIn("src/app/(dashboard)/contracts/actions.ts", context)

    def test_optional_context_cannot_be_promoted_to_writable(self):
        worker = self.worker()
        source = {"assignment": {
            "context_paths": ["src/services/ContractService.ts", "src/app/(dashboard)/contracts/actions.ts"],
            "scope_keys": ["src/services/ContractService.ts"],
            "verified_readonly_callsite_paths": [],
        }, "verified_readonly_callsite_paths": ["src/app/(dashboard)/contracts/actions.ts"]}
        _, unsafe = worker._repository_snapshot_with_safety(source=source, base_commit=SHA)
        self.assertNotIn("src/app/(dashboard)/contracts/actions.ts", unsafe)
        tampered = {"assignment": dict(source["assignment"]), "verified_readonly_callsite_paths": [
            "src/components/Other.tsx",
        ]}
        with self.assertRaisesRegex(PermissionError, "invalid pinned call-site"):
            worker._repository_snapshot_with_safety(source=tampered, base_commit=SHA)


if __name__ == "__main__":
    unittest.main()
