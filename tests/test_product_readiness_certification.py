import unittest

from ai_product_factory.product_readiness_certification import (
    CertificationEvidenceError, certify_product_readiness,
    conservative_verified_manifest,
)

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
    def test_all_nineteen_fake_sha_links_cannot_produce_a_certificate(self):
        # Regression for the original false-positive: these references name
        # a SHA, but no criterion-specific independent audit has executed.
        out=self.certify()
        self.assertFalse(out.assessment.ready)
        self.assertEqual(out.assessment.status,"not_ready")
        self.assertEqual(sum(len(x) for x in out.report["criteria"].values()),19)
        self.assertEqual(out.report["source_snapshot"]["validation_run_id"],7)
        self.assertIn(out.evidence_digest,out.assessment.assessment_ref)
        self.assertEqual(sum(
            item["status"]=="passed"
            for domain in out.report["criteria"].values()
            for item in domain.values()
        ),0)
        self.assertTrue(any(
            "no independently verified source" in x
            for x in out.assessment.blockers
        ))

    def test_conservative_baseline_verifies_real_ci_and_blocks_other_18(self):
        data=github()
        evidence=conservative_verified_manifest(
            repository=REPO,assessed_commit=SHA,github_get=lambda p:data[p]
        )
        out=self.certify(data=data,evidence=evidence)
        self.assertFalse(out.assessment.ready)
        self.assertEqual(out.report["criteria"]["test_strategy"]["unit_integration"]["status"],"passed")
        self.assertEqual(sum(
            item["status"]=="passed"
            for domain in out.report["criteria"].values()
            for item in domain.values()
        ),1)
        self.assertEqual(out.report["criteria"]["test_strategy"]["regression_gates"]["status"],"partial")
        self.assertEqual(sum("/" in x for x in out.assessment.blockers),18)
        self.assertEqual(len(out.assessment.blockers),24)
        self.assertEqual(out.report["criteria"]["test_strategy"]["unit_integration"]["attestation"],{
            "kind":"github_exact_sha_validate","repository":REPO,
            "assessed_commit":SHA,"run_id":7,"jobs":["factory-acceptance","test"],
        })

    def test_attestation_scope_and_source_identity_cannot_be_spoofed(self):
        data=github()
        evidence=conservative_verified_manifest(
            repository=REPO,assessed_commit=SHA,github_get=lambda p:data[p]
        )
        trusted=evidence["criteria"]["test_strategy"]["unit_integration"]
        trusted["evidence"]=["untrusted-caller-supplied"]
        out=self.certify(data=data,evidence=evidence)
        checked=out.report["criteria"]["test_strategy"]["unit_integration"]
        self.assertEqual(checked["status"],"passed")
        self.assertNotIn("untrusted-caller-supplied",checked["evidence"])
        self.assertIn(SHA,checked["evidence"][0])
        for mutation in (
            {"run_id":8},{"assessed_commit":"b"*40},
            {"kind":"github_made_up"},{"repository":"attacker/repo"},
            {"jobs":["test"]},
        ):
            evidence=conservative_verified_manifest(
                repository=REPO,assessed_commit=SHA,github_get=lambda p:data[p]
            )
            evidence["criteria"]["test_strategy"]["unit_integration"]["attestation"].update(mutation)
            out=self.certify(data=data,evidence=evidence)
            self.assertEqual(out.report["criteria"]["test_strategy"]["unit_integration"]["status"],"failed")
            self.assertFalse(out.assessment.ready)

    def test_ci_attestation_cannot_approve_security_or_browser_claims(self):
        data=github()
        evidence=conservative_verified_manifest(
            repository=REPO,assessed_commit=SHA,github_get=lambda p:data[p]
        )
        attestation=evidence["criteria"]["test_strategy"]["unit_integration"]["attestation"]
        for domain,key in (
            ("security","authn_authz"),
            ("observability_operations","health"),
            ("product_experience","accessibility"),
            ("functional_completeness","critical_journeys"),
        ):
            evidence["criteria"][domain][key]={
                "status":"passed","evidence":["sha:"+SHA],
                "reason":"purported independent review",
                "verification_state":{
                    "security":"reviewed",
                    "observability_operations":"observed",
                    "product_experience":"observed",
                    "functional_completeness":"reviewed",
                }[domain],
                "attestation":attestation,
            }
        out=self.certify(data=data,evidence=evidence)
        for domain,key in (
            ("security","authn_authz"),
            ("observability_operations","health"),
            ("product_experience","accessibility"),
            ("functional_completeness","critical_journeys"),
        ):
            self.assertEqual(out.report["criteria"][domain][key]["status"],"failed")
        self.assertFalse(out.assessment.ready)

    def test_malformed_criterion_status_fails_closed_without_crashing(self):
        evidence=manifest()
        evidence["criteria"]["security"]["authn_authz"]["status"]=["passed"]
        out=self.certify(evidence=evidence)
        self.assertEqual(out.report["criteria"]["security"]["authn_authz"]["status"],"missing")
        self.assertFalse(out.assessment.ready)
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
