from __future__ import annotations

from types import SimpleNamespace
import unittest
from pathlib import Path

from ai_product_factory.journey_delivery_binding import JourneyBinding, JourneyBindingBlocked, assert_preview_belongs_to_journey, build_main_snapshot_binding, resolve_pending_main_snapshot
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

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

    def test_v2_explicit_main_target_and_preview_only_routes_are_distinct(self):
        preview_only = JourneyBinding.parse(binding(), project_id=PROJECT, request_id=REQUEST, repository=REPO)
        self.assertEqual(preview_only.implementation_pr_base_ref(), "preview/crm171-contracts")
        main_target = JourneyBinding.parse(binding(preview_base_ref="main"), project_id=PROJECT,
                                           request_id=REQUEST, repository=REPO)
        self.assertEqual(main_target.implementation_pr_base_ref(), "main")
        self.assertNotEqual(main_target.preview_branch_prefix, "preview/crm22-admin-audit-next")
        with self.assertRaisesRegex(JourneyBindingBlocked, "journey_release_destination_not_main"):
            JourneyBinding.parse(binding(release_base_ref="preview/crm22-admin-audit-next"),
                                 project_id=PROJECT, request_id=REQUEST, repository=REPO)

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

    def test_pending_v2_source_is_resolved_from_policy_and_verified_twice(self):
        calls=[]
        class GitHub:
            repository=REPO
            def get_branch_sha(self, ref): calls.append(ref); return "c"*40
        result=resolve_pending_main_snapshot(journey={"id":JOURNEY,"request_id":REQUEST,"state":"awaiting_source"},
            project={"id":PROJECT,"repository":REPO,"manifest":{"journey_delivery_binding_v2":{"enabled":True,"version":2,"digest":"d"*64,"source_mode":"main_snapshot","preview_base_ref":"preview/crm171-contracts","release_base_ref":"main"}}},
            control={"state":"running","generation":17},github=GitHub())
        self.assertEqual(result["source_commit"],"c"*40)
        self.assertEqual(calls,["main","main"])

    def test_rotated_policy_pins_exact_main_and_preview_on_both_reads(self):
        class GitHub:
            repository = REPO
            def __init__(self):
                self.refs = {"main": "c"*40, "preview/crm209-delivery-v3": "c"*40}
                self.calls = []
            def get_branch_sha(self, ref):
                self.calls.append(ref)
                return self.refs[ref]
        gh = GitHub()
        project = {"id": PROJECT, "repository": REPO, "manifest": {
            "journey_delivery_binding_v2": {"enabled": True, "version": 3, "digest": "d"*64,
                "source_mode": "main_snapshot", "preview_base_ref": "preview/crm209-delivery-v3",
                "release_base_ref": "main", "source_commit_pin": "c"*40,
                "preview_base_source_sha": "c"*40}}}
        journey = {"id": JOURNEY, "request_id": REQUEST, "state": "awaiting_source"}
        control = {"state": "running", "generation": 17}
        result = resolve_pending_main_snapshot(journey=journey, project=project, control=control, github=gh)
        self.assertEqual(result["source_commit"], "c"*40)
        self.assertEqual(gh.calls, ["main", "preview/crm209-delivery-v3", "main", "preview/crm209-delivery-v3"])
        gh.refs["preview/crm209-delivery-v3"] = "b"*40
        with self.assertRaisesRegex(JourneyBindingBlocked, "journey_source_preview_pin_mismatch"):
            resolve_pending_main_snapshot(journey=journey, project=project, control=control, github=gh)
        gh.refs["preview/crm209-delivery-v3"] = "c"*40
        gh.refs["main"] = "b"*40
        with self.assertRaisesRegex(JourneyBindingBlocked, "journey_source_preview_pin_mismatch"):
            resolve_pending_main_snapshot(journey=journey, project=project, control=control, github=gh)
        del project["manifest"]["journey_delivery_binding_v2"]["preview_base_source_sha"]
        with self.assertRaisesRegex(JourneyBindingBlocked, "journey_source_preview_pin_mismatch"):
            resolve_pending_main_snapshot(journey=journey, project=project, control=control, github=gh)

    def test_supersession_migration_restricts_state_acl_epoch_and_second_start(self):
        sql = (Path(__file__).resolve().parents[1] /
               "supabase/migrations/20261101130000_journey_v2_safe_supersession.sql").read_text().lower()
        for expected in ("journey.superseded", "factory_supersede_inactive_journey_v2",
                         "factory_journey_supersessions_v2", "factory_console_operators",
                         "control_quiescent", "p_expected_generation", "p_expected_version",
                         "journey_source_preview_pin_mismatch" if False else "preview_base_source_sha",
                         "project has an unfinished v2 journey", "project has an incompatible v2 journey",
                         "lease_owner", "output_commit is not null", "service_role",
                         "production_release_authorized',false"):
            self.assertIn(expected, sql)
        self.assertNotIn("security definer", sql)
        self.assertNotIn("gh pr merge", sql)

    def test_persisted_v2_run_stays_v2_when_new_intake_flag_is_disabled(self):
        queue=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        raw=binding()
        raw["source_proof_digest"]="d"*64
        snapshot={"text":"CRM #171 authorized request","digest":"e"*64}
        def get(path):
            if path.startswith("factory_runs?"): return [{"journey_id":JOURNEY}]
            if path.startswith("factory_projects?"): return [{"repository":REPO}]
            if path.startswith("factory_journeys?"): return [{"id":JOURNEY,"project_id":PROJECT,"request_id":REQUEST,"request_digest":"e"*64,"state":"source_bound","binding":raw,"request_snapshot":snapshot,"execution_generation":17}]
            raise AssertionError(path)
        queue._get=get
        journey,context=queue._v2_journey_context(run_id="run",project_id=PROJECT,
            context={"manifest":{"journey_delivery_binding_v2":{"enabled":False}}})
        self.assertEqual(journey,JOURNEY)
        self.assertEqual(context["journey_request"],snapshot)
