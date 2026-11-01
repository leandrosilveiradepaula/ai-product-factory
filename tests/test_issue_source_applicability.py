from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.issue_source_applicability import (
    IssueSourceMismatch, check_reported_existing_code, unique_issue,
)
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

SHA="a"*40
REPO="leandrosilveiradepaula/crm-infodive"
REQUEST="Implementar a issue #171 do repositório leandrosilveiradepaula/crm-infodive: corrigir ContractService.getContracts sem IN gigante."
ISSUE="Auditoria após o PR #170: `ContractService.getContracts` busca todos os IDs e os envia de uma só vez em `.in('deal_id', visibleIds)`, em toda página de contratos."


def evidence(code, *,complete=True,omitted=None):
    return {"assessed_commit":SHA, "inspected_files":[
        {"path":"src/services/ContractService.ts","content":code,
         "complete":complete,"assessed_commit":SHA},
    ],"omitted_paths":omitted or []}


class IssueSourceApplicabilityTests(unittest.TestCase):
    def check(self, code, **kwargs):
        return check_reported_existing_code(
            request=REQUEST, repository=REPO, source_sha=SHA,
            issue_number=171, issue_body=ISSUE,source_evidence=evidence(code,**kwargs),
        )

    def test_genuine_reported_expression_must_exist_at_frozen_sha(self):
        result=self.check("const q = db.from('contracts').in('deal_id', visibleIds);")
        self.assertEqual(result["status"],"reported_code_present")
        self.assertEqual(result["checked_anchor_count"],1)

    def test_crm171_real_incident_blocks_before_paid_planning(self):
        with self.assertRaisesRegex(IssueSourceMismatch,"journey_reported_existing_code_not_at_source"):
            self.check("const query = db.from('contracts').select('*,authorized_deal:deals!inner(id)');")

    def test_crm209_qualified_declaration_is_not_a_literal_call_site(self):
        request=("Implementar a issue #209 do repositório "
                 "leandrosilveiradepaula/crm-infodive e revisar ContractService.getContracts")
        issue=("No SHA atual, `ContractService.getContracts(organizationId)` "
               "utiliza createAdminClient e filtra apenas por tenant.")
        frozen="export class ContractService { static async getContracts(organizationId: string) { return []; } }"
        ev=evidence(frozen)
        result=check_reported_existing_code(
            request=request,repository=REPO,source_sha=SHA,issue_number=209,
            issue_body=issue,source_evidence=ev)
        self.assertEqual(result["status"],"reported_code_present")
        self.assertEqual(result["checked_anchor_count"],1)

    def test_crm209_declaration_must_be_at_exact_class_path_and_name(self):
        request=("Implementar a issue #209 do repositório "
                 "leandrosilveiradepaula/crm-infodive e revisar ContractService.getContracts")
        issue="O serviço `ContractService.getContracts(organizationId)` utiliza createAdminClient."
        cases=(
            ("export class ContractService { async other(organizationId: string) {} }","src/services/ContractService.ts"),
            ("export class ContractService { static async getContracts(userId: string) {} }","src/services/ContractService.ts"),
            ("export class OtherService { static async getContracts(organizationId: string) {} }","src/services/ContractService.ts"),
            ("export class ContractService { static async getContracts(organizationId: string) {} }","src/services/OtherService.ts"),
        )
        for code,path in cases:
            with self.subTest(path=path,code=code):
                ev=evidence(code)
                ev["inspected_files"][0]["path"]=path
                with self.assertRaisesRegex(IssueSourceMismatch,"journey_reported_existing_code_not_at_source"):
                    check_reported_existing_code(
                        request=request,repository=REPO,source_sha=SHA,issue_number=209,
                        issue_body=issue,source_evidence=ev)

    def test_crm209_declaration_does_not_relax_exact_sql_call_check(self):
        request=("Implementar a issue #209 do repositório "
                 "leandrosilveiradepaula/crm-infodive e revisar ContractService.getContracts")
        issue="A consulta `.in('deal_id', visibleIds)` usa uma lista de IDs."
        ev=evidence("export class ContractService { static async getContracts(organizationId: string) {} }")
        with self.assertRaisesRegex(IssueSourceMismatch,"journey_reported_existing_code_not_at_source"):
            check_reported_existing_code(
                request=request,repository=REPO,source_sha=SHA,issue_number=209,
                issue_body=issue,source_evidence=ev)

    def test_truncated_or_omitted_code_cannot_prove_absence(self):
        self.assertEqual(self.check("const other=1;",complete=False)["status"],"insufficient_source_evidence")
        self.assertEqual(self.check("const other=1;",omitted=["src/other.ts"])["status"],"insufficient_source_evidence")

    def test_no_asserted_code_never_fabricates_completion(self):
        result=check_reported_existing_code(
            request=REQUEST,repository=REPO,source_sha=SHA,issue_number=171,
            issue_body="Precisa implementar novos testes com paginação.",
            source_evidence=evidence("export class ContractService {}"),
        )
        self.assertEqual(result["status"],"no_asserted_existing_code")

    def test_no_cross_repo_or_ambiguous_issue_identity(self):
        self.assertIsNone(unique_issue("issue #171",REPO))
        self.assertIsNone(unique_issue(REQUEST+" issue #22",REPO))
        self.assertIsNone(unique_issue(REQUEST,"untrusted/other"))
        with self.assertRaises(IssueSourceMismatch):
            check_reported_existing_code(
                request=REQUEST, repository=REPO, source_sha=SHA, issue_number=22,
                issue_body=ISSUE,source_evidence=evidence(".in('deal_id', visibleIds)"),
            )

    def test_quoted_desired_code_without_existing_claim_not_required(self):
        result=check_reported_existing_code(
            request=REQUEST,repository=REPO,source_sha=SHA,issue_number=171,
            issue_body="Criar função `validateSomething(input)` para novos requisitos.",
            source_evidence=evidence("export class ContractService {}"),
        )
        self.assertEqual(result["status"],"no_asserted_existing_code")

    def test_no_issue_text_or_ref_is_written_to_error(self):
        with self.assertRaises(IssueSourceMismatch) as raised:
            self.check("export class ContractService {}")
        self.assertNotIn("ContractService",str(raised.exception))
        self.assertNotIn("171",str(raised.exception))

    def test_v2_live_context_fetches_issue_only_at_exact_repository(self):
        # The method under test is executed without live paid model or network.
        queue=object.__new__(SupabaseRuntimeQueue)
        binding={
            "journey_id":"61bc7a1f-dcab-4616-9ce7-1ff28a0aa915",
            "project_id":"e2ea3201-e9a3-489f-bf14-916aecc7de09",
            "request_id":"d49060c4-69a0-c58d-4254-54a40003f607",
            "execution_generation":17,"policy_version":2,"policy_digest":"a"*64,
            "repository":REPO,"source_commit":SHA,"source_ref":"main",
            "source_mode":"main_snapshot",
            "integration_branch":"factory/journey-61bc7a1f-dcab-4616-9ce7-1ff28a0aa915",
            "preview_base_ref":"preview/crm171-delivery-v2",
            "release_base_ref":"main","binding_version":2
        }
        from unittest.mock import patch
        github=MagicMock()
        github.repository=REPO
        github.get_issue.return_value=SimpleNamespace(number=171,body=ISSUE)
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter",return_value=github), \
             patch("ai_product_factory.journey_source_inspection.inspect_journey_source",return_value=evidence("const q=db.in('deal_id', visibleIds);")):
            result=queue._live_journey_context({
                "journey_binding_v2":binding,
                "journey_request":{"text":REQUEST},
            })
        self.assertEqual(result["current_state_facts"]["source_issue_applicability"]["status"],"reported_code_present")
        github.get_issue.assert_called_once_with(171)


if __name__=="__main__":
    unittest.main()
