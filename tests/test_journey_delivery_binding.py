from __future__ import annotations

from types import SimpleNamespace
import unittest
from pathlib import Path

from ai_product_factory.journey_delivery_binding import JourneyBinding, JourneyBindingBlocked, assert_preview_belongs_to_journey, build_main_snapshot_binding

JOURNEY = "61bc7a1f-dcab-4616-9ce7-1ff28a0aa915"
PROJECT = "e2ea3201-e9a3-489f-bf14-916aecc7de09"
REQUEST = "d49060c4-69a0-c58d-4254-54a40003f607"
REPO = "leandrosilveiradepaula/crm-infodive"

def binding(**changes):
    result = {"journey_id": JOURNEY, "project_id": PROJECT, "request_id": REQUEST,
        "execution_generation": 17, "policy_version": 2, "policy_digest": "a" * 64,
        "repository": REPO, "source_commit": "b" * 40, "source_ref": "main",
        "source_mode": "main_snapshot", "integration_branch": "factory/journey-" + JOURNEY,
        "preview_base_ref": "preview/crm171-contracts", "release_base_ref": "main", "binding_version": 2}
    result.update(changes)
    return result

class JourneyBindingTests(unittest.TestCase):
    def test_real_incident_new_request_has_its_own_source_and_destination(self):
        parsed = JourneyBinding.parse(binding(), project_id=PROJECT, request_id=REQUEST, repository=REPO)
        self.assertEqual(parsed.preview_base_ref, "preview/crm171-contracts")
        self.assertNotEqual(parsed.preview_base_ref, "preview/crm22-admin-audit-next")
        self.assertEqual(parsed.source_commit, "b" * 40)

    def test_cross_issue_preview_destination_and_cross_project_are_rejected(self):
        policy = SimpleNamespace(base_ref="preview/crm22-admin-audit-next")
        item = SimpleNamespace(journey_binding=binding(), project_id=PROJECT, request_id=REQUEST, repository=REPO)
        with self.assertRaisesRegex(JourneyBindingBlocked, "journey_preview_destination_mismatch"):
            assert_preview_belongs_to_journey(item, policy)
        with self.assertRaisesRegex(JourneyBindingBlocked, "journey_binding_cross_request"):
            JourneyBinding.parse(binding(request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"), project_id=PROJECT, request_id=REQUEST, repository=REPO)

    def test_force_push_like_sha_and_unsafe_destination_are_rejected(self):
        for changed in ({"source_commit": "A" * 40}, {"integration_branch": "factory/other"}, {"preview_base_ref": "preview/../crm22"}):
            with self.subTest(changed=changed), self.assertRaises(JourneyBindingBlocked):
                JourneyBinding.parse(binding(**changed), project_id=PROJECT, request_id=REQUEST, repository=REPO)

    def test_candidate_migration_has_atomic_intake_bind_acl_and_structural_propagation(self):
        sql = (Path(__file__).resolve().parents[1] / "supabase/migrations/20261030150000_journey_delivery_binding_v2.sql").read_text()
        for clause in ("create table if not exists public.factory_journeys", "unique(project_id,request_id)",
                       "factory_enqueue_journey_intake_v2", "factory_bind_journey_source_v2",
                       "for update", "journey.source_bound", "factory_propagate_journey_binding_v2",
                       "SECURITY INVOKER", "from public,anon,authenticated", "to service_role"):
            self.assertIn(clause.lower(), sql.lower())
        self.assertNotIn("security definer", sql.lower())
        self.assertNotIn("gh pr merge", sql.lower())

    def test_bound_identity_requires_generation_policy_and_version(self):
        for changed in ({"execution_generation": 0}, {"policy_digest": "bad"}, {"binding_version": 1}):
            with self.subTest(changed=changed), self.assertRaises(JourneyBindingBlocked):
                JourneyBinding.parse(binding(**changed), project_id=PROJECT, request_id=REQUEST, repository=REPO)

    def test_documental_pr_is_not_needed_when_policy_explicitly_authorizes_main_snapshot(self):
        result=build_main_snapshot_binding(journey_id=JOURNEY,project_id=PROJECT,request_id=REQUEST,
            repository=REPO,generation=17,main_sha="c"*40,
            policy={"enabled":True,"version":2,"digest":"d"*64,"source_mode":"main_snapshot",
                    "preview_base_ref":"preview/crm171-contracts","release_base_ref":"main"})
        self.assertEqual(result["source_commit"],"c"*40)
        self.assertEqual(result["source_ref"],"main")
        self.assertTrue(result["source_proof_digest"])
