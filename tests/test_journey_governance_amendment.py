from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from ai_product_factory.journey_delivery_binding import JourneyBinding
from ai_product_factory.journey_governance_amendment import (
    verify_scoped_governance_amendment, constrain_scoped_amendment,
)
from ai_product_factory.work_unit_context import build_context_packet

SOURCE = "fea4669258fcd832c7e187e7b00c1c5fb4d90a76"
MERGE = "d63fa1ad8f1ffd252fe7df27f93a562e7184e8f6"
JOURNEY = "88e94d11-4ada-4630-aa6a-fbf2c5665b2b"
REQUEST = "380ba6e9-be62-4911-8c32-c4762552c0c0"
PROJECT = "2d30e00a-ff72-4044-b838-011c263ed672"
SET = "c105550f-3f2e-4623-bf21-f93f335deb62"
RUN = "e95970d2-1fc0-43cb-b649-2a07ab1a229d"
UNIT = "a82b7582-5b93-40de-998e-dee62a531134"
REPO = "leandrosilveiradepaula/crm-infodive"
DOC = "docs/codex/CURRENT_TASK.md"
AUTH = """# CURRENT_TASK — CRM #171: contratos escaláveis (Factory journey V2)

## Arquivos permitidos exclusivamente para a issue #171

- `src/services/ContractService.ts`;
- `src/services/ContractService.test.ts` (se necessário, criar);
- testes diretamente relacionados em `test/**` ou `tests/**`.

---

# CURRENT_TASK — CRM #200: Service Desk
"""

def fixture():
    raw = {
        "journey_id": JOURNEY, "project_id": PROJECT, "request_id": REQUEST,
        "execution_generation": 16, "policy_version": 2, "policy_digest": "a"*64,
        "repository": REPO, "source_commit": SOURCE, "source_ref": "main",
        "source_mode": "main_snapshot", "integration_branch": "factory/journey-"+JOURNEY,
        "preview_base_ref": "preview/crm171-delivery-v2",
        "release_base_ref": "main", "binding_version": 2,
    }
    binding = JourneyBinding.parse(raw, project_id=PROJECT, request_id=REQUEST, repository=REPO)
    amendment = {
        "version":1, "pr_number":208, "issue_number":171,
        "source_commit":SOURCE, "merge_commit":MERGE, "journey_id":JOURNEY,
        "request_id":REQUEST, "change_set_id":SET, "run_id":RUN, "work_unit_id":UNIT,
    }
    github=MagicMock()
    github.repository=REPO
    github.get_pull_request.return_value=SimpleNamespace(
        merged=True,state="closed",base_ref="main",base_sha=SOURCE,
        merge_commit_sha=MERGE,head_repository=REPO,head_sha="e6d4eaac2b3b1872ddc96a1a1dbdb6b0294782be",
    )
    github.compare_commits.return_value={
        "status":"ahead","ahead_by":1,"behind_by":0,"files":[DOC],
    }
    github.get_pull_request_files.return_value=(DOC,)
    github.get_branch_sha.return_value=MERGE
    github.get_file_text.side_effect=lambda path,ref: AUTH if ref==MERGE else "# CURRENT_TASK — old\n"
    return binding,amendment,github

class GovernanceAmendmentTests(TestCase):
    def test_exact_merger_and_document_authenticates_scoped_files(self):
        binding,amendment,github=fixture()
        proof=verify_scoped_governance_amendment(
            github=github,binding=binding,amendment=amendment,
            change_set_id=SET,observed_ref_sha=MERGE,
        )
        self.assertEqual(proof["authorized_paths"],[
            "src/services/ContractService.ts","src/services/ContractService.test.ts",
        ])
        self.assertEqual(proof["source_commit"],SOURCE)
        self.assertEqual(proof["merge_commit"],MERGE)
        source={
            "journey_request":{"text":"Implementar a issue #171 com isolamento"},
            "assignment":{"scope_keys":[
                "src/services/ContractService.ts",
                "contract-query-call-sites",
                "src/services/ContractService.test.ts",
            ]},
            "human_decisions":[],"constraints":[],
            "task":{"title":"ContractService","description":"test","acceptance_criteria":[]},
        }
        limited=constrain_scoped_amendment(source=source,proof=proof,run_id=RUN,work_unit_id=UNIT)
        self.assertEqual(limited["assignment"]["scope_keys"],proof["authorized_paths"])
        self.assertEqual(source["assignment"]["scope_keys"][1],"contract-query-call-sites")
        packet=build_context_packet(source=limited,impact={},base_commit=SOURCE,
           branch="factory/cs-c105550f/issue171-contracts-scalable-read")
        self.assertEqual(packet.payload["governance_amendment"]["merge_commit"],MERGE)
        self.assertEqual(packet.payload["repository"]["exact_base_commit"],SOURCE)

    def test_reject_modified_main_and_non_documentary_changes(self):
        binding,a,g=fixture()
        cases=[
            lambda a,g: g.compare_commits.return_value.update(files=[DOC,"src/services/ContractService.ts"]),
            lambda a,g: g.compare_commits.return_value.update(ahead_by=2),
            lambda a,g: setattr(g.get_pull_request.return_value,"merged",False),
            lambda a,g: setattr(g.get_pull_request.return_value,"base_sha",MERGE),
            lambda a,g: setattr(g.get_pull_request.return_value,"head_repository","attacker/repo"),
            lambda a,g: None,
            lambda a,g: g.get_branch_sha.configure_mock(return_value=SOURCE),
            lambda a,g: a.update(issue_number=22),
            lambda a,g: a.update(change_set_id=RUN),
        ]
        # One independent fixture per scenario. Any mismatch fails closed.
        for index,mutate in enumerate(cases):
            b,v,h=fixture()
            if index==5:
                h.get_pull_request_files.return_value=(DOC,"AGENTS.md")
            else:
                mutate(v,h)
            with self.subTest(index=index), self.assertRaises(PermissionError):
                verify_scoped_governance_amendment(
                    github=h,binding=b,amendment=v,change_set_id=SET,observed_ref_sha=MERGE,
                )

    def test_scope_does_not_authorize_another_issue_or_work_unit(self):
        b,a,g=fixture()
        proof=verify_scoped_governance_amendment(
            github=g,binding=b,amendment=a,change_set_id=SET,observed_ref_sha=MERGE,
        )
        src={"journey_request":{"text":"Implementar a issue #22"},
             "assignment":{"scope_keys":["src/services/ContractService.ts"]}}
        with self.assertRaises(PermissionError):
            constrain_scoped_amendment(source=src,proof=proof,run_id=RUN,work_unit_id=UNIT)
        src["journey_request"]["text"]="Implementar a issue #171"
        with self.assertRaises(PermissionError):
            constrain_scoped_amendment(source=src,proof=proof,run_id=RUN,work_unit_id=JOURNEY)

    def test_no_implicit_scope_for_missing_exact_files(self):
        b,a,g=fixture()
        proof=verify_scoped_governance_amendment(
            github=g,binding=b,amendment=a,change_set_id=SET,observed_ref_sha=MERGE,
        )
        src={"journey_request":{"text":"Implementar a issue #171"},
             "assignment":{"scope_keys":["src/services/OtherService.ts","contract-query-call-sites"]}}
        with self.assertRaises(PermissionError):
            constrain_scoped_amendment(source=src,proof=proof,run_id=RUN,work_unit_id=UNIT)

    def test_must_fail_if_source_is_a_mutated_binding(self):
        b,a,g=fixture()
        with self.assertRaises(PermissionError):
            verify_scoped_governance_amendment(
                github=g,binding=replace(b,source_commit=MERGE),
                amendment=a,change_set_id=SET,observed_ref_sha=MERGE)
