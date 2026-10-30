"""Exact native-CI repin evidence is scoped and never grants extra files."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from ai_product_factory.change_set_store import SupabaseChangeSetStore
from ai_product_factory.work_unit_context import build_context_packet
from ai_product_factory.verified_repin import verified_repin

PROJECT="2d30e00a-ff72-4044-b838-011c263ed672"
SHA="a"*40
BEFORE="b"*40
REPOSITORY="owner/crm"
BRANCH="preview/hardening-release-candidate"

TARGET={
    "schema_version":1,"mode":"open_pr_candidate","repository":REPOSITORY,
    "sha":SHA,"branch":BRANCH,"candidate_pr_number":56,
    "repin_policy":{"enabled":True,"native_ci":{"schema_version":1,
        "event":"pull_request","workflow_id":372542929,
        "workflow_name":"CRM validation"}},
}
CONTROL={"project_id":PROJECT,"state":"running","generation":12,"version":11}
EVENT={
    "id":1924,"project_id":PROJECT,
    "actor_type":"system","actor_ref":"factory-candidate-reconciler",
    "event_type":"project.delivery_target.reconciled",
    "payload":{
        "project_key":"crm","repository":REPOSITORY,"branch":BRANCH,
        "source":"github_actions_exact_sha","status":"updated",
        "old_sha":BEFORE,"new_sha":SHA,"ci_sha":SHA,"pr_number":56,
        "ci_run_id":40143764314,"generation":12,"version":11,
        "compare_status":"ahead","ahead_by":1,"behind_by":0,
    },
}


def store_with(target=TARGET,control=CONTROL,events=(EVENT,)):
    store=SupabaseChangeSetStore.__new__(SupabaseChangeSetStore)
    requests=[]
    store._rpc=lambda _name,_params:{
        "project_key":"crm","repository":REPOSITORY,
        "project_kind":"existing","work_unit_id":"work-1",
        "assignment":{"scope_keys":["src/app/(dashboard)/service-desk/page.tsx"]},
    }
    def get(path):
        requests.append(path)
        if path.startswith("factory_projects?"):
            return [{"id":PROJECT,"project_kind":"existing",
                     "manifest":{"delivery_target":deepcopy(target)}}]
        if path.startswith("factory_project_execution_controls?"):
            return [deepcopy(control)]
        if path.startswith("factory_audit_events?"):
            return [deepcopy(e) for e in events]
        if path.startswith("factory_change_set_work_units?"):
            return [{"task_id":"task-1"}]
        if path.startswith("factory_tasks?"):
            return [{"scope_keys":["src/app/(dashboard)/service-desk/page.tsx"]}]
        raise AssertionError("Unexpected database query: "+path)
    store._get=get
    return store,requests


def packet(source,sha=SHA):
    return build_context_packet(
        source={**source,"plan_task_key":"service-desk",
                "task":{"title":"Service Desk entry"}},
        impact={},base_commit=sha,branch="factory/change-set-123",
        repository_snapshot={"AGENTS.md":"safe read-only instructions"},
    )


class RepinContextTests(unittest.TestCase):
    def test_current_generation_audit_is_passed_to_exact_sha_model_context(self):
        store,requests=store_with()
        source=store.context_source("run-1")
        proof=source["repin_evidence"]
        self.assertEqual(proof["audit_event_id"],1924)
        self.assertEqual(proof["ci_run_id"],40143764314)
        self.assertEqual(proof["sha"],SHA)
        self.assertEqual(proof["generation"],12)
        self.assertTrue(any("project_id=eq."+PROJECT in q
            and "event_type=in.(project.delivery_target.reconciled,project.delivery_target.replaced)" in q
            for q in requests))
        actual=packet(source).payload
        self.assertEqual(actual["repository"]["delivery_repin_evidence"],proof)
        self.assertEqual(actual["repository"]["write_scopes"],
                         ["src/app/(dashboard)/service-desk/page.tsx"])
        self.assertNotIn("delivery_repin_evidence",str(actual["sandbox"]))
        self.assertNotIn("service_role",json.dumps(actual))

    def test_repin_must_match_current_project_epoch_and_exact_ci(self):
        variations=(
            ("event_project",{"project_id":"wrong"},None,None),
            ("event_actor",{"actor_ref":"untrusted"},None,None),
            ("event_source",{},None,{"source":"manual"}),
            ("event_sha",{},None,{"new_sha":"c"*40}),
            ("ci_sha",{},None,{"ci_sha":"c"*40}),
            ("ci_run",{},None,{"ci_run_id":0}),
            ("pr_number",{},None,{"pr_number":57}),
            ("generation",{},None,{"generation":11}),
            ("version",{},None,{"version":10}),
            ("branch",{},None,{"branch":"preview/other"}),
            ("not_ahead",{},None,{"compare_status":"diverged"}),
            ("epoch_drift",{},{"generation":13},None),
            ("version_drift",{},{"version":12},None),
        )
        for name,change,ctl_change,receipt_change in variations:
            with self.subTest(name=name):
                event=deepcopy(EVENT)
                event.update(change)
                if receipt_change:
                    event["payload"].update(receipt_change)
                control={**CONTROL,**(ctl_change or {})}
                proof=verified_repin(
                    project_id=PROJECT,project_key="crm",
                    repository=REPOSITORY,target=TARGET,
                    control=control,events=[event],
                )
                self.assertIsNone(proof)

    def test_authorized_replacement_receipt_binds_current_source_epoch(self):
        target={**TARGET,"sha":SHA,"branch":BRANCH,"candidate_pr_number":203}
        changed={
            "id":2026,"project_id":PROJECT,
            "actor_type":"system","actor_ref":"factory-candidate-switch",
            "event_type":"project.delivery_target.replaced",
            "payload":{
                "status":"replaced","project_key":"crm","repository":REPOSITORY,
                "old_sha":BEFORE,"new_sha":SHA,
                "old_branch":"preview/old","new_branch":BRANCH,
                "old_pr_number":202,"new_pr_number":203,
                "issue_number":22,"request_id":"authorized-issue-22",
                "ci_sha":SHA,"ci_run_id":40876464121,
                "generation":12,"version":11,
            }
        }
        store,queries=store_with(target=target,events=[changed])
        source=store.context_source("run-1")
        proof=source["repin_evidence"]
        self.assertEqual(proof["source_transition"],"project.delivery_target.replaced")
        self.assertEqual(proof["candidate_pr_number"],203)
        self.assertEqual(proof["sha"],SHA)
        self.assertEqual(packet(source).payload["repository"]["delivery_repin_evidence"],proof)
        self.assertTrue(any("event_type=in.(" in query for query in queries))

    def test_replacement_receipt_cannot_be_forged_or_from_previous_generation(self):
        base={
            "id":2026,"project_id":PROJECT,
            "actor_type":"system","actor_ref":"factory-candidate-switch",
            "event_type":"project.delivery_target.replaced",
            "payload":{
                "status":"replaced","project_key":"crm","repository":REPOSITORY,
                "old_sha":BEFORE,"new_sha":SHA,
                "old_branch":"preview/old","new_branch":BRANCH,
                "old_pr_number":202,"new_pr_number":56,
                "issue_number":22,"request_id":"authorized-issue-22",
                "ci_sha":SHA,"ci_run_id":40876464121,
                "generation":12,"version":11,
            }
        }
        cases=(
            ("actor_ref","untrusted","event"),
            ("actor_ref","factory-candidate-reconciler","event"),
            ("generation",11,"payload"),
            ("version",10,"payload"),
            ("ci_sha","c"*40,"payload"),
            ("new_branch","preview/other","payload"),
            ("old_pr_number",56,"payload"),
            ("new_pr_number",203,"payload"),
            ("request_id","","payload"),
            ("new_sha","c"*40,"payload"),
        )
        for field,value,where in cases:
            row=deepcopy(base)
            row[field]=value if where=="event" else row[field] if field in row else None
            if where=="payload":
                row["payload"][field]=value
            with self.subTest(field=field,value=value):
                self.assertIsNone(verified_repin(
                    project_id=PROJECT,project_key="crm",
                    repository=REPOSITORY,target=TARGET,
                    control=CONTROL,events=[row]))

    def test_missing_and_disabled_audit_fail_closed(self):
        for target,events in ((TARGET,()),({**TARGET,"repin_policy":{"enabled":False}},(EVENT,))):
            with self.subTest(target=target):
                store,_=store_with(target=target,events=events)
                source=store.context_source("run-1")
                self.assertIsNone(source["repin_evidence"])
                self.assertNotIn("delivery_repin_evidence",packet(source).payload["repository"])

    def test_forged_or_stale_proof_is_not_embedded(self):
        source=store_with()[0].context_source("run-1")
        for variant in (
            {"sha":"c"*40},{"ci_sha":"c"*40},
            {"project_key":"another"},{"repository":"owner/other"},
            {"candidate_pr_number":57},{"audit_event_id":0},
            {"generation":0},{"branch":"preview/other"}
        ):
            with self.subTest(variant=variant):
                changed={**source,"repin_evidence":{**source["repin_evidence"],**variant}}
                with self.assertRaises(PermissionError):
                    packet(changed)
        with self.assertRaises(PermissionError):
            packet(source,sha="c"*40)

    def test_legacy_projects_do_not_gain_new_authorization(self):
        store,_=store_with(target={"schema_version":1})
        source=store.context_source("run-1")
        self.assertIsNone(source["repin_evidence"])


if __name__=="__main__":
    unittest.main()
