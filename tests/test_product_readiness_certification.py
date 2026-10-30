import unittest

from ai_product_factory.product_readiness_certification import CertificationEvidenceError, certify_product_readiness

SHA = "a" * 40
REPO = "leandrosilveiradepaula/ai-product-factory"

def github():
    p = "/repos/" + REPO
    return {p:{"default_branch":"main"}, p+"/git/ref/heads/main":{"object":{"sha":SHA}},
      p+"/actions/runs?head_sha="+SHA+"&event=push&per_page=100":{"total_count":1,"workflow_runs":[{"id":7,"name":"validate","path":".github/workflows/validate.yml","event":"push","head_sha":SHA,"head_branch":"main","status":"completed","conclusion":"success"}]},
      p+"/actions/runs/7/jobs?per_page=100":{"total_count":2,"jobs":[{"run_id":7,"head_sha":SHA,"name":"test","status":"completed","conclusion":"success"},{"run_id":7,"head_sha":SHA,"name":"factory-acceptance","status":"completed","conclusion":"success"}]}}

def manifest(status="passed"):
    keys={"security":("authn_authz","data_access_boundaries","secrets_dependencies"),"observability_operations":("health","traceability","recovery_alerting"),"test_strategy":("unit_integration","critical_e2e","regression_gates"),"product_experience":("surface_inventory","responsive","accessibility","states"),"documentation":("setup_configuration","operations","release_rollback"),"functional_completeness":("requirements_inventory","mock_noop_demo_inventory","critical_journeys")}
    state={"security":"executed","observability_operations":"executed","test_strategy":"executed","product_experience":"observed","documentation":"reviewed","functional_completeness":"reviewed"}
    return {"criteria":{d:{k:{"status":status,"evidence":["github:"+REPO+"@"+SHA+":"+d+"/"+k],"verification_state":state[d],"reason":"independent evidence"} for k in ks} for d,ks in keys.items()}}

class ProductReadinessCertificationTests(unittest.TestCase):
    def certify(self, data=None, evidence=None):
        data=data or github()
        return certify_product_readiness(repository=REPO,assessed_commit=SHA,manifest=evidence or manifest(),github_get=lambda p:data[p])
    def test_all_nineteen_criteria_produce_exact_sha_passing_assessment(self):
        out=self.certify()
        self.assertTrue(out.assessment.ready); self.assertEqual(out.assessment.status,"passed")
        self.assertEqual(sum(len(x) for x in out.report["criteria"].values()),19)
        self.assertEqual(out.report["source_snapshot"]["validation_run_id"],7)
        self.assertIn(out.evidence_digest,out.assessment.assessment_ref)
    def test_partial_missing_and_external_gate_are_not_ready_blockers(self):
        evidence=manifest(); evidence["criteria"]["security"]["authn_authz"]["status"]="partial"; evidence["criteria"]["test_strategy"]["critical_e2e"]["status"]="missing"; evidence["criteria"]["product_experience"]["responsive"]["status"]="external_gate"
        out=self.certify(evidence=evidence)
        self.assertFalse(out.assessment.ready)
        self.assertTrue(any(x.startswith("security/authn_authz: partial") for x in out.assessment.blockers))
        self.assertTrue(any(x.startswith("test_strategy/critical_e2e: missing") for x in out.assessment.blockers))
        self.assertTrue(any(x.startswith("product_experience/responsive: external_gate") for x in out.assessment.blockers))
    def test_sha_drift_other_ci_and_incomplete_ci_fail_before_persistence(self):
        data=github(); data["/repos/"+REPO+"/git/ref/heads/main"]["object"]["sha"]="b"*40
        with self.assertRaises(CertificationEvidenceError): self.certify(data)
        data=github(); data["/repos/"+REPO+"/actions/runs?head_sha="+SHA+"&event=push&per_page=100"]["workflow_runs"][0]["conclusion"]="failure"
        with self.assertRaises(CertificationEvidenceError): self.certify(data)
        data=github(); data["/repos/"+REPO+"/actions/runs/7/jobs?per_page=100"]["jobs"][1]["head_sha"]="c"*40
        with self.assertRaises(CertificationEvidenceError): self.certify(data)
    def test_unbound_and_absent_evidence_never_passes(self):
        evidence=manifest(); evidence["criteria"]["security"]["authn_authz"]["evidence"]=["github:unbound"]
        self.assertFalse(self.certify(evidence=evidence).assessment.ready)
        evidence=manifest(); del evidence["criteria"]["documentation"]["operations"]
        out=self.certify(evidence=evidence)
        self.assertFalse(out.assessment.ready)
        self.assertIn("documentation/operations: missing criterion record is required",out.assessment.blockers)
    def test_digest_is_stable_but_detects_evidence_change(self):
        self.assertEqual(self.certify().evidence_digest,self.certify().evidence_digest)
        evidence=manifest(); evidence["criteria"]["documentation"]["operations"]["reason"]="changed"
        self.assertNotEqual(self.certify().evidence_digest,self.certify(evidence=evidence).evidence_digest)

if __name__=="__main__": unittest.main()
