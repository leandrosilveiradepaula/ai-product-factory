"""B4 read-only audit rejects fabricated journeys, release, and greenfield."""
from __future__ import annotations
import unittest

from scripts.audit_block1_real_journeys_readonly import (
    JourneyEvidenceUnverifiable, assess, collect, CRM_REPO,
)

PID = "2d30e00a-ff72-4044-b838-011c263ed672"
JID = "bb14e150-2c7e-423b-8e5d-e211dab6225c"
CRM = [{"id": PID, "project_key": "crm-infodive",
        "repository": CRM_REPO, "is_active": True}]
JOURNEY = {
    "id": JID, "project_id": PID, "state": "preview_verified",
    "request_source": "github-owner",
    "issue_repository": "leandrosilveiradepaula/ai-product-factory",
    "issue_number": 1055, "candidate_commit": "a" * 40,
    "preview_merge_sha": None, "production_release_sha": None,
}
RETIRED = [{"project_key": "infodive-service-desk",
            "project_kind": "greenfield", "repository": "owner/service-desk",
            "is_active": True}]


class RealJourneyWitnessTests(unittest.TestCase):
    def audit(self, journeys=None, greenfield=None, projects=None):
        return assess(projects=CRM if projects is None else projects,
                      journeys=[JOURNEY] if journeys is None else journeys,
                      greenfield=RETIRED if greenfield is None else greenfield)

    def test_real_existing_preview_is_not_release_or_e2e(self):
        result = self.audit()
        self.assertEqual(result["crm_journey_state"], "preview_verified")
        self.assertEqual(result["crm_blocker"], "human_merge_or_release_unverified")
        self.assertFalse(result["crm_production_release_sha_observed"])
        self.assertFalse(result["critical_journeys_certified"])
        self.assertFalse(result["critical_e2e_certified"])
        self.assertFalse(result["product_ready"])
        self.assertEqual(result["paid_calls"], 0)
        self.assertEqual(result["writes"], 0)

    def test_release_sha_alone_never_certifies_full_journey(self):
        result = self.audit(journeys=[{**JOURNEY, "production_release_sha": "b" * 40}])
        self.assertTrue(result["crm_production_release_sha_observed"])
        self.assertEqual(result["crm_blocker"],
                         "independent_full_journey_e2e_unverified")
        self.assertFalse(result["critical_e2e_certified"])

    def test_retired_service_desk_never_satisfies_greenfield(self):
        result = self.audit()
        self.assertEqual(result["other_active_greenfield_count"], 0)
        self.assertFalse(result["retired_service_desk_eligible"])
        self.assertEqual(result["greenfield_blocker"],
                         "legitimate_new_greenfield_target_missing")

    def test_real_greenfield_exists_but_not_automatically_approved(self):
        other = {"project_key": "legitimate-product",
                 "project_kind": "greenfield", "repository": "owner/legitimate",
                 "is_active": True}
        result = self.audit(greenfield=RETIRED + [other])
        self.assertEqual(result["other_active_greenfield_count"], 1)
        self.assertEqual(result["greenfield_blocker"],
                         "legitimate_human_authorized_greenfield_journey_unverified")
        self.assertFalse(result["critical_journeys_certified"])

    def test_absent_or_forged_owner_start_cannot_count(self):
        no_journey = self.audit(journeys=[])
        self.assertEqual(no_journey["crm_blocker"], "legitimate_existing_start_missing")
        for bad in [
            {**JOURNEY, "project_id": "0" * 36},
            {**JOURNEY, "issue_repository": "attacker/repo"},
            {**JOURNEY, "issue_number": 0},
            {**JOURNEY, "candidate_commit": "not-a-commit"},
        ]:
            with self.subTest(bad=bad), self.assertRaises(JourneyEvidenceUnverifiable):
                self.audit(journeys=[bad])

    def test_duplicate_and_parallel_journeys_refuse_single_receipt(self):
        with self.assertRaises(JourneyEvidenceUnverifiable):
            self.audit(journeys=[JOURNEY, JOURNEY])
        other = {**JOURNEY, "id": "11111111-1111-4111-8111-111111111111"}
        with self.assertRaises(JourneyEvidenceUnverifiable):
            self.audit(journeys=[JOURNEY, other])

    def test_project_cannot_be_replaced_or_inactivated(self):
        for projects in [
            [],
            [{**CRM[0], "repository": "attacker/repo"}],
            [{**CRM[0], "is_active": False}],
        ]:
            with self.subTest(projects=projects), self.assertRaises(JourneyEvidenceUnverifiable):
                self.audit(projects=projects)

    def test_reader_is_read_only_and_selects_exact_project(self):
        calls = []
        def get(path):
            calls.append(path)
            if path.startswith("factory_projects?") and "project_key=eq.crm-infodive" in path:
                return CRM
            if path.startswith("factory_journeys?"):
                self.assertIn("project_id=eq." + PID, path)
                return [JOURNEY]
            if path.startswith("factory_projects?") and "project_kind=eq.greenfield" in path:
                return RETIRED
            raise AssertionError("unexpected privileged or mutating read")
        result = collect(get)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("?" in query and "select=" in query for query in calls))
        self.assertEqual(result["crm_journey_id"], JID)


if __name__ == "__main__":
    unittest.main()
