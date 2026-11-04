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


V2_JOURNEY="bb14e150-2c7e-423b-8e5d-e211dab6225c"
V2_BRANCH="factory/journey-"+V2_JOURNEY
V2_PREVIEW="preview/crm209-delivery-v4"
V2_PROJECT="2d30e00a-ff72-4044-b838-011c263ed672"
V2_REQUEST="1c19ce32-b42a-9e0a-29af-0767474b9244"


def v2_source():
    src=source()
    src["delivery_target"]=None
    src["repin_evidence"]=None
    src["project_id"]=V2_PROJECT
    src["request_id"]=V2_REQUEST
    src["journey_id"]=V2_JOURNEY
    src["repair"]["branch"]=V2_BRANCH
    src["journey_binding"]={
        "journey_id":V2_JOURNEY,"project_id":V2_PROJECT,"request_id":V2_REQUEST,
        "execution_generation":19,"policy_version":4,"policy_digest":"d"*64,
        "repository":REPO,"source_commit":SOURCE,"source_ref":"main",
        "source_mode":"main_snapshot","integration_branch":V2_BRANCH,
        "preview_branch_prefix":"preview/journey-bb14e150",
        "preview_base_ref":V2_PREVIEW,"release_base_ref":"main",
        "binding_version":2,
    }
    return src


class V2GitHub(GitHub):
    def __init__(self):
        super().__init__()
        self.pr.head_ref=V2_BRANCH
        self.pr.base_ref=V2_PREVIEW
        self.preview_sha=SOURCE

    def get_branch_sha(self,branch):
        if branch==V2_BRANCH:
            return self.branch_sha
        if branch==V2_PREVIEW:
            return self.preview_sha
        if branch=="main":
            return SOURCE
        raise AssertionError("unexpected ref "+str(branch))


def v2_evidence(src=None,gh=None):
    return verify_existing_ci_repair_candidate(
        source=src if src is not None else v2_source(),
        base_commit=CANDIDATE,integration_branch=V2_BRANCH,
        github=gh if gh is not None else V2GitHub(),
    )


class JourneyV2CIRepairCandidateTests(unittest.TestCase):
    def test_v2_native_repair_uses_immutable_journey_not_legacy_project_target(self):
        src=v2_source()
        proof=v2_evidence(src)
        self.assertEqual(proof["candidate_commit"],CANDIDATE)
        self.assertEqual(proof["base_preview_sha"],SOURCE)
        self.assertEqual(proof["base_preview_branch"],V2_PREVIEW)
        self.assertEqual(proof["journey_id"],V2_JOURNEY)
        self.assertEqual(proof["execution_generation"],19)
        src["ci_repair_evidence"]=proof
        packet=context(src).payload["repository"]
        self.assertEqual(packet["ci_repair_candidate_evidence"],proof)
        self.assertNotIn("delivery_repin_evidence",packet)
        self.assertEqual(packet["write_scopes"],SCOPES)

    def test_v2_forged_journey_or_reintroduced_v1_target_is_rejected(self):
        for field,value in (
            ("journey_id","b"*36),
            ("request_id","00000000-0000-0000-0000-000000000000"),
            ("project_id","00000000-0000-0000-0000-000000000000"),
            ("integration_branch","factory/journey-00000000-0000-0000-0000-000000000000"),
            ("preview_base_ref","main"),
            ("source_commit","c"*40),
        ):
            with self.subTest(field=field):
                src=v2_source()
                if field in ("journey_id","request_id","project_id"):
                    src[field]=value
                else:
                    src["journey_binding"][field]=value
                with self.assertRaises(PermissionError):
                    v2_evidence(src)

        src=v2_source()
        src["delivery_target"]=source()["delivery_target"]
        with self.assertRaises(PermissionError):
            v2_evidence(src)

    def test_v2_preview_ref_drift_and_pr_drift_fail_closed(self):
        gh=V2GitHub()
        gh.preview_sha="c"*40
        with self.assertRaises(PermissionError):
            v2_evidence(gh=gh)
        for field,value in (
            ("base_ref","main"),
            ("head_ref",BRANCH),
            ("head_sha","c"*40),
            ("head_repository","owner/other"),
            ("draft",True),
        ):
            with self.subTest(field=field):
                gh=V2GitHub()
                setattr(gh.pr,field,value)
                with self.assertRaises(PermissionError):
                    v2_evidence(gh=gh)

    def test_v2_context_packet_rejects_tampered_provenance(self):
        src=v2_source()
        proof=v2_evidence(src)
        for field,value in (
            ("journey_id","00000000-0000-0000-0000-000000000000"),
            ("execution_generation",20),
            ("binding_version",1),
            ("base_preview_sha","c"*40),
            ("base_preview_branch",PREVIEW),
        ):
            with self.subTest(field=field):
                tampered={**src,"ci_repair_evidence":{**proof,field:value}}
                with self.assertRaises(PermissionError):
                    context(tampered)
        with self.assertRaises(PermissionError):
            context({**src,"ci_repair_evidence":proof,"delivery_target":source()["delivery_target"]})


if __name__=="__main__":
    unittest.main()
