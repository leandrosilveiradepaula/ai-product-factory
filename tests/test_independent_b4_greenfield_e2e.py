"""B4 trusted source boundary tests: no Supabase/LLM/GitHub network."""
import copy
import unittest

from ai_product_factory.independent_b4_greenfield_e2e import (
    B4GreenfieldE2EBlocked, verify_b4_greenfield_e2e,
)
from ai_product_factory.product_readiness_certification import VerifiedCriterionEvidence

FACTORY="leandrosilveiradepaula/ai-product-factory"
TARGET="example/product"
SHA="a"*40
BROWSER_SHA="b"*40
CANDIDATE="c"*40
PID="11111111-1111-1111-1111-111111111111"
CSID="22222222-2222-2222-2222-222222222222"
RUN="33333333-3333-3333-3333-333333333333"
TASK="44444444-4444-4444-4444-444444444444"
SNAP="55555555-5555-5555-5555-555555555555"
REQUEST="66666666-6666-6666-6666-666666666666"
URL="https://example-product-git-factory.vercel.app"

class Fixture:
    def __init__(self):
        self.tables={
            "factory_projects":[{
                "id":PID,"project_key":"generic-product","project_kind":"greenfield",
                "repository":TARGET,"is_active":True,
                "manifest":{"source":"factory-console","preview":{
                    "required":True,"provider":"vercel","mode":"github"},
                    "human_decisions":[{"gate_id":SNAP,"resolved_at":"2026-11-16T01:00:00Z",
                                        "resolved_by":"authorized-operator"}]},
            }],
            "factory_change_sets":[{
                "id":CSID,"project_id":PID,"root_task_id":TASK,
                "release_run_id":RUN,"status":"ci_pending",
                "candidate_commit":CANDIDATE,"integration_branch":"factory/change-set-22222222",
                "metadata":{"integration_release_request":{
                    "candidate_commit":CANDIDATE,"branch":"factory/change-set-22222222",
                    "pr_number":42,"issue_number":9},
                    "integration_epoch_receipt":{"candidate_commit":CANDIDATE,
                         "project_id":PID,"generation":7,"wave":3}},
            }],
            "factory_runs":[{
                "id":RUN,"task_id":TASK,"status":"release_policy_blocked",
                "branch_name":"factory/change-set-22222222","candidate_commit":CANDIDATE,
                "metadata":{"source":"change-set","change_set_id":CSID,
                            "execution_generation":7},
            }],
            "factory_evaluations":[
                {"id":str(i),"eval_type":kind,"status":status,
                 "baseline_ref":CANDIDATE,"result":body}
                for i,(kind,status,body) in enumerate([
                    ("github_ci","success",{"head_sha":CANDIDATE,"pr":42,"ci_state":"success"}),
                    ("quality_gate","success",{"passed":True}),
                    ("specialist_security","passed",{}),
                    ("specialist_qa","passed",{}),
                    ("specialist_operations","passed",{}),
                ],start=1)
            ]+[
                {"id":"failedeval","eval_type":"browser_e2e","status":"failure",
                 "baseline_ref":URL,"result":{"checks":["page_load"],
                     "detail":"preview_application_origin_mismatch","preview_url":URL}},
                {"id":"successeval","eval_type":"browser_e2e","status":"success",
                 "baseline_ref":URL,"result":{"checks":["page_load","http_status",
                     "body_visible","expected_text","console_clean"],
                     "detail":None,"preview_url":URL}},
            ],
            "factory_project_state_snapshots":[{
                "id":SNAP,"project_id":PID,"observed_stage":"verification","run_id":None,
                "evidence":{"candidate_commit":CANDIDATE,"target_repository":TARGET,
                    "preview":{"url":URL,"status":"browser_verified","provider":"vercel",
                        "verifier_factory_commit":BROWSER_SHA,
                        "browser_verifier_run_id":98765432,"browser_request_id":REQUEST}},
                "source_status":{"github_target":"verified","vercel_preview":"resolved",
                                  "browser_visual_validation":"success"},
                "constraints":{"product_ready_inferred":False,
                               "production_merge_authorized":False},
            }],
            "factory_audit_events":[
                {"id":3,"event_type":"preview.browser_evidence_recorded","payload":{
                    "status":"success","preview_url":URL}},
                {"id":2,"event_type":"preview.oidc_origin_mismatch.browser_verified_resume",
                 "payload":{"candidate_commit":CANDIDATE,"release_authorized":False,
                            "original_browser_failure_preserved":True}},
            ],
        }
        self.gh={
            "/repos/"+FACTORY+"/actions/runs/98765432":{
                "id":98765432,"name":"Console evidence "+REQUEST,
                "path":".github/workflows/console-browser-evidence.yml",
                "event":"workflow_dispatch","head_sha":BROWSER_SHA,
                "status":"completed","conclusion":"success",
                "repository":{"full_name":FACTORY},
            },
            "/repos/"+FACTORY+"/actions/runs/98765432/jobs?per_page=100":{
                "total_count":1,"jobs":[{"name":"browser-evidence",
                    "head_sha":BROWSER_SHA,"status":"completed","conclusion":"success",
                    "steps":[{"name":"Verify exact protected Preview","conclusion":"success"}]}],
            },
            "/repos/"+FACTORY+"/compare/"+BROWSER_SHA+"..."+SHA:{
                "status":"ahead","behind_by":0,"ahead_by":3,
            },
        }

    def cp(self,path):
        return copy.deepcopy(self.tables[path.split("?",1)[0]])

    def github(self,path):
        return copy.deepcopy(self.gh[path])

    def verify(self):
        return verify_b4_greenfield_e2e(
            repository=FACTORY,assessed_commit=SHA,
            github_get=self.github,control_plane_get=self.cp,
        )


class IndependentB4E2E(unittest.TestCase):
    def test_positive_is_only_critical_e2e_never_full_journey_or_release(self):
        fixture=Fixture()
        proof=fixture.verify()
        self.assertEqual(proof.candidate_commit,CANDIDATE)
        self.assertEqual(proof.original_pr,42)
        self.assertEqual(proof.visual_witness_id,SNAP)
        criterion=proof.criterion()
        self.assertIs(type(criterion),VerifiedCriterionEvidence)
        self.assertEqual((criterion.domain,criterion.criterion),
                         ("test_strategy","critical_e2e"))
        self.assertEqual(criterion.verification_state,"executed")
        receipt=proof.receipt()
        self.assertFalse(receipt["critical_journeys_certified"])
        self.assertFalse(receipt["production_merge_observed"])
        self.assertFalse(receipt["greenfield_product_ready_inferred"])
        self.assertFalse(receipt["production_release_authorized"])
        self.assertEqual((receipt["writes"],receipt["paid_calls"]),(0,0))
        self.assertTrue(all(SHA in x for x in criterion.evidence))
        self.assertNotIn("email",str(receipt).lower())

    def test_missing_and_ambiguous_greenfields_fail_closed(self):
        f=Fixture()
        f.tables["factory_projects"]=[]
        with self.assertRaises(B4GreenfieldE2EBlocked):f.verify()
        f=Fixture()
        f.tables["factory_projects"]*=2
        with self.assertRaises(B4GreenfieldE2EBlocked):f.verify()

    def test_spoofed_human_decision_and_external_demo_are_denied(self):
        for mutation in [
            lambda f:f.tables["factory_projects"][0]["manifest"].update(source="test-demo"),
            lambda f:f.tables["factory_projects"][0]["manifest"].pop("human_decisions"),
            lambda f:f.tables["factory_projects"][0]["manifest"]["preview"].update(required=False),
        ]:
            with self.subTest(mutation=mutation):
                f=Fixture();mutation(f)
                with self.assertRaises(B4GreenfieldE2EBlocked):f.verify()

    def test_stale_and_unbound_provenance_denied(self):
        for mutation in [
            lambda f:f.tables["factory_change_sets"][0].update(candidate_commit=BROWSER_SHA),
            lambda f:f.tables["factory_change_sets"][0].update(status="failed"),
            lambda f:f.tables["factory_runs"][0].update(status="failed"),
            lambda f:f.tables["factory_runs"][0].update(branch_name="other"),
            lambda f:f.tables["factory_change_sets"][0]["metadata"]["integration_epoch_receipt"].update(wave=1),
            lambda f:f.tables["factory_change_sets"][0]["metadata"]["integration_release_request"].update(pr_number=0),
            lambda f:f.tables["factory_evaluations"][0]["result"].update(head_sha=BROWSER_SHA),
            lambda f:f.tables["factory_evaluations"][1].update(status="failure"),
            lambda f:f.tables["factory_evaluations"].pop(3),
        ]:
            with self.subTest(mutation=mutation):
                f=Fixture();mutation(f)
                with self.assertRaises(B4GreenfieldE2EBlocked):f.verify()

    def test_page_only_and_fake_browser_pass_do_not_certify(self):
        for mutation in [
            lambda f:f.tables["factory_evaluations"][-1]["result"].update(checks=["page_load"]),
            lambda f:f.tables["factory_evaluations"][-1].update(status="failure"),
            lambda f:f.tables["factory_evaluations"][-1]["result"].update(
                preview_url="https://other.vercel.app"),
            lambda f:f.tables["factory_project_state_snapshots"][0]["source_status"].update(
                browser_visual_validation="failure"),
            lambda f:f.tables["factory_project_state_snapshots"][0]["constraints"].update(
                product_ready_inferred=True),
            lambda f:f.tables["factory_audit_events"][1]["payload"].update(
                release_authorized=True),
            lambda f:f.tables["factory_audit_events"].clear(),
            lambda f:f.gh["/repos/"+FACTORY+"/actions/runs/98765432"].update(
                conclusion="failure"),
            lambda f:f.gh["/repos/"+FACTORY+"/actions/runs/98765432/jobs?per_page=100"][
                "jobs"][0]["steps"][0].update(conclusion="skipped"),
            lambda f:f.gh["/repos/"+FACTORY+"/compare/"+BROWSER_SHA+"..."+SHA].update(
                behind_by=1),
        ]:
            with self.subTest(mutation=mutation):
                f=Fixture();mutation(f)
                with self.assertRaises(B4GreenfieldE2EBlocked):f.verify()

    def test_no_backend_creation_or_paid_model_path(self):
        import inspect
        from ai_product_factory import independent_b4_greenfield_e2e as module
        src=inspect.getsource(module)
        for forbidden in (
            "apply_migration(", "create_project(", "merge_pull_request(",
            "execute_model(", "service_role_key", "FACTORY_PRIMARY_MODEL_ENABLED",
            "update public.factory_evaluations",
        ):
            self.assertNotIn(forbidden,src)
        self.assertIn("production_merge_observed",src)

if __name__=="__main__":
    unittest.main()
