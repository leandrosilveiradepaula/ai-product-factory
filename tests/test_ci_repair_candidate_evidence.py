"""Keep CI repair SHA lineage independent of project source repins."""
import unittest
from copy import deepcopy
from types import SimpleNamespace

from ai_product_factory.ci_repair_candidate_evidence import (
    verify_existing_ci_repair_candidate,
)
from ai_product_factory.work_unit_context import build_context_packet

SOURCE="a"*40
CANDIDATE="b"*40
REPO="owner/crm"
PREVIEW="preview/hardening-release-candidate"
BRANCH="factory/change-set-673a2fc7"
SCOPES=["src/app/(dashboard)/service-desk/page.tsx",
        "src/lib/service-desk/entry-guard.ts"]
REPAIR_ID="d1ba00fc-827d-4930-a04d-bcae57ef42f0"


def source():
    return {
        "project_kind":"existing","project_key":"crm-infodive",
        "repository":REPO,
        "change_set_id":"673a2fc7-5f8c-40da-8bec-18ff6bb7eeed",
        "delivery_target":{
            "repository":REPO,"branch":PREVIEW,"sha":SOURCE,
            "mode":"open_pr_candidate","schema_version":1,
            "candidate_pr_number":56,
        },
        "repin_evidence":{
            "kind":"control_plane_native_ci_repin",
            "sha":SOURCE,"ci_sha":SOURCE,"audit_event_id":1924,
        },
        "assignment":{"scope_keys":SCOPES,"context_paths":[]},
        "repair":{
            "repair_kind":"ci","candidate_commit":CANDIDATE,
            "branch":BRANCH,"pr_number":197,
            "attempt":1,"max_attempts":3,
            "repair_request_id":REPAIR_ID,
            "write_scopes":SCOPES,
        },
        "task":{"title":"Repair exact native CI failure"},
    }


class GitHub:
    repository=REPO
    def __init__(self):
        self.branch_sha=CANDIDATE
        self.pr=SimpleNamespace(
            number=197,state="open",merged=False,draft=False,
            head_sha=CANDIDATE,head_ref=BRANCH,base_ref=PREVIEW,
            head_repository=REPO,
        )
        self.calls=0
    def get_branch_sha(self,branch):
        assert branch==BRANCH
        return self.branch_sha
    def get_pull_request(self,pr):
        self.calls+=1
        # The live PR provider returns its own immutable PR number; the
        # implementation must refuse a forged request for a different PR.
        return self.pr


def evidence(src=None,gh=None):
    src=src or source()
    gh=gh or GitHub()
    return verify_existing_ci_repair_candidate(
        source=src,base_commit=CANDIDATE,
        integration_branch=BRANCH,github=gh,
    )


def context(src):
    return build_context_packet(
        source=src,impact={},
        base_commit=CANDIDATE,
        branch="factory/cs-673a2fc7/ci-repair-1",
        repository_snapshot={"AGENTS.md":"governance"},
    )


class CIRepairCandidateEvidenceTests(unittest.TestCase):
    def test_exact_live_pr_proves_repair_without_project_repin_on_candidate(self):
        src=source()
        gh=GitHub()
        proof=evidence(src,gh)
        self.assertEqual(gh.calls,1)
        self.assertEqual(proof["candidate_commit"],CANDIDATE)
        self.assertEqual(proof["base_preview_sha"],SOURCE)
        src["ci_repair_evidence"]=proof
        pkt=context(src).payload
        repo=pkt["repository"]
        self.assertEqual(repo["ci_repair_candidate_evidence"],proof)
        self.assertNotIn("delivery_repin_evidence",repo)
        self.assertEqual(repo["write_scopes"],SCOPES)

    def test_forged_or_drifted_repair_lineage_is_rejected(self):
        mutations=[
            ("project_kind","platform"),
            ("repository","owner/other"),
            ("repair.candidate_commit",SOURCE),
            ("repair.pr_number",57),
            ("repair.branch","factory/other"),
            ("repair.repair_request_id","not-uuid"),
            ("repair.attempt",4),
            ("repair.max_attempts",4),
            ("repair.write_scopes",["src/other.ts"]),
            ("assignment.scope_keys",["src/other.ts"]),
            ("delivery_target.repository","owner/other"),
        ]
        for path,value in mutations:
            with self.subTest(path=path):
                src=source()
                node=src
                keys=path.split(".")
                for key in keys[:-1]:
                    node=node[key]
                node[keys[-1]]=value
                if path=="project_kind":
                    self.assertIsNone(evidence(src))
                else:
                    with self.assertRaises(PermissionError):
                        evidence(src)

    def test_stale_branch_or_pr_cannot_authorize_any_candidate(self):
        mutations=[
            ("branch_sha","c"*40),
            ("pr.head_sha","c"*40),
            ("pr.head_ref","factory/other"),
            ("pr.base_ref","main"),
            ("pr.head_repository","owner/other"),
            ("pr.state","closed"),
            ("pr.merged",True),
            ("pr.draft",True),
        ]
        for path,value in mutations:
            with self.subTest(path=path):
                gh=GitHub()
                if path.startswith("pr."):
                    setattr(gh.pr,path[3:],value)
                else:
                    setattr(gh,path,value)
                with self.assertRaises(PermissionError):
                    evidence(gh=gh)

    def test_repair_packet_requires_live_attestation_before_model(self):
        src=source()
        with self.assertRaisesRegex(PermissionError,"verified CI repair"):
            context(src)
        proof=evidence(src)
        for change in (
            {"candidate_commit":SOURCE},
            {"base_preview_sha":CANDIDATE},
            {"pr_number":200},
            {"write_scopes":["src/other.ts"]},
            {"attempt":2},
        ):
            with self.subTest(change=change):
                changed={**src,"ci_repair_evidence":{**proof,**change}}
                with self.assertRaises(PermissionError):
                    context(changed)
        with self.assertRaises(PermissionError):
            context({**src,"repair":{},"ci_repair_evidence":proof})

    def test_normal_repin_still_requires_exact_original_source(self):
        src=source()
        src.pop("repair")
        src.pop("ci_repair_evidence",None)
        with self.assertRaisesRegex(PermissionError,"repin evidence"):
            context(src)


if __name__=="__main__":
    unittest.main()
