"""Regression for real CRM #22 planning against old Service Desk #194.

Pinned candidate governance remains a write boundary even after a valid,
persisted human approval. No paid model, migration or cross-repo write here.
"""
import unittest
from unittest.mock import Mock, patch

from ai_product_factory.candidate_source_evidence import (
    source_issue_scope_alignment, collect_candidate_source_evidence,
)
from ai_product_factory.source_scope_admission import SourceScopeBlocked
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue


REPO = "leandrosilveiradepaula/crm-infodive"
SHA = "a" * 40
MAIN_SHA = "b" * 40
TICK = chr(96)
TASK = (
    "# CURRENT_TASK\n"
    "## Tarefa autorizada (24/10/2026) - entrada do Service Desk\n"
    "Critério: https://github.com/leandrosilveiradepaula/crm-infodive/issues/194\n"
    "Escopo: https://github.com/leandrosilveiradepaula/crm-infodive/issues/194"
    "#issuecomment-6390960882\n"
    "Issue operacional da Factory #1055, nao autoriza RBAC.\n"
    "Somente " + TICK + "src/lib/service-desk/entry-guard.ts" + TICK + ".\n"
)
REQUEST = "Concluir as falhas comprovadas da issue #22 do CRM Infodive."
APPROVED = {
    "gate_id": "e5166b92-30a4-4e70-a8eb-15eb6201e0d2",
    "response": "Autorizo avaliação da issue #22 do CRM Infodive; sem RLS ou migrations.",
    "decisions": [{"decision_key": "authorize_issue_22_access_scope"}],
}


class IssueUrlScopeTests(unittest.TestCase):
    def test_old_candidate_and_approved_new_issue_are_a_conflict(self):
        self.assertEqual(source_issue_scope_alignment(
            TASK, REQUEST, repository=REPO
        ), {
            "status": "conflict", "requested_issue": 22, "authorized_issue": 194,
        })

    def test_same_issue_is_matched_without_granting_writes(self):
        self.assertEqual(source_issue_scope_alignment(
            TASK, "Validar CRM issue #194.", repository=REPO
        )["status"], "matched")

    def test_unqualified_request_does_not_imply_repository_authorization(self):
        self.assertEqual(source_issue_scope_alignment(
            TASK, "Verificar a issue #22.", repository=REPO
        )["status"], "unverified")

    def test_cross_repo_issue_link_is_not_crm_authority(self):
        other = (
            "## Tarefa autorizada (27/10/2026)\n"
            "https://github.com/leandrosilveiradepaula/ai-product-factory/issues/194\n"
        )
        self.assertEqual(source_issue_scope_alignment(
            other, REQUEST, repository=REPO
        )["status"], "unverified")

    def test_two_current_repository_issue_urls_are_ambiguous(self):
        doc = TASK + "https://github.com/leandrosilveiradepaula/crm-infodive/issues/200\n"
        self.assertEqual(source_issue_scope_alignment(
            doc, REQUEST, repository=REPO
        )["status"], "unverified")

    def test_approved_request_cannot_add_candidate_code_to_write_scope(self):
        github = Mock()
        github.repository = REPO
        github.list_file_paths.return_value = ("src/lib/service-desk/entry-guard.ts",)
        github.get_file_text.return_value = "export const deny = () => false;\n"
        evidence = collect_candidate_source_evidence(
            TASK, github, sha=SHA, continuation_request=REQUEST,
        )
        self.assertEqual(evidence["issue_scope_alignment"]["status"], "conflict")
        self.assertEqual(
            [entry["path"] for entry in evidence["inspected_files"]],
            ["src/lib/service-desk/entry-guard.ts"],
        )
        self.assertNotIn(
            "src/lib/server-authorization.ts", evidence["governance_scope_paths"]
        )

    def test_existing_prose_issue_matching_remains_compatible(self):
        doc = (
            "## Tarefa autorizada - CRM\n"
            "Origem: CRM issue #22.\n"
            + TICK + "src/lib/server-authorization.ts" + TICK + "\n"
        )
        self.assertEqual(source_issue_scope_alignment(
            doc, "Concluir CRM issue #22", repository=REPO
        )["status"], "matched")


class DurableBeforePaidPreflightTests(unittest.TestCase):
    def test_approved_gate_does_not_override_old_pinned_sha_before_model(self):
        manifest = {
            "delivery_target": {"sha": SHA},
            "continuation_request": {"summary": REQUEST},
            "human_decisions": [APPROVED],
        }
        queue = SupabaseRuntimeQueue(
            url="https://example.supabase.co", service_role_key="test"
        )
        events = []

        def rpc(name, payload):
            events.append((name, payload))
            if name == "factory_claim_next_run":
                return {
                    "run_id": "run-crm", "task_id": "task-crm",
                    "project_id": "project-crm", "project_key": "crm-infodive",
                    "stages": ["reconciliation", "gap_analysis", "planning"],
                    "context": {"manifest": manifest}, "execution_generation": 13,
                }
            if name in {"factory_assert_claimed_run_epoch", "factory_finish_run"}:
                return None
            raise AssertionError("unexpected write " + name)

        queue._rpc = rpc
        queue._reconciliation_context = Mock(side_effect=lambda _id, ctx: ctx)
        queue._get = Mock(return_value=[{
            "repository": REPO, "project_kind": "existing", "manifest": manifest,
        }])
        with patch(
            "ai_product_factory.supabase_runtime_queue.PinnedNonproductionTarget.parse"
        ) as pin, patch(
            "ai_product_factory.supabase_runtime_queue.GitHubRestAdapter"
        ) as github_class:
            pin.return_value = Mock(
                sha=SHA, branch="preview/old", candidate_pr_number=56
            )
            github = github_class.return_value
            github.get_branch_sha.return_value = MAIN_SHA
            github.get_file_text.side_effect = (
                lambda path, ref: TASK if path == "docs/codex/CURRENT_TASK.md"
                else "# AGENTS"
            )
            with self.assertRaises(SourceScopeBlocked) as cm:
                queue.claim_next("worker")
            self.assertEqual(
                cm.exception.code, "source_authorization_issue_mismatch"
            )
            github.list_file_paths.assert_not_called()
            github.get_file_text.assert_any_call(
                "docs/codex/CURRENT_TASK.md", ref=SHA
            )
        self.assertEqual([name for name, _ in events], [
            "factory_claim_next_run", "factory_assert_claimed_run_epoch",
            "factory_finish_run",
        ])
        self.assertEqual(events[-1][1]["p_error"],
                         "reconciliation_source_authorization_issue_mismatch")
        self.assertNotIn("Autorizo", repr(events))
        self.assertEqual(queue._get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
