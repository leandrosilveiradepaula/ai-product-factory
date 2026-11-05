"""Deterministic offline denial matrix for native V2 independent read-only audit."""
from __future__ import annotations

import copy
import hashlib
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from uuid import UUID

from ai_product_factory.github_owner_start import (
    FACTORY_REPO, OWNER_ID, OWNER_LOGIN, ISSUE_NUMBER, request_uuid,
)
from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubPullRequest
from ai_product_factory.native_v2_journey_audit import (
    EvidenceBlocked, audit_existing_native_v2, safe_paths,
    _check_owner_intake, _check_lineage, _check_delivery,
)
from scripts.audit_native_v2_journey import resolve_target

PID = "00000000-0000-4000-8000-000000000001"
JID = "00000000-0000-4000-8000-000000000002"
ROOT = "00000000-0000-4000-8000-000000000003"
RELEASE = "00000000-0000-4000-8000-000000000004"
SOURCE = "00000000-0000-4000-8000-000000000005"
CS = "00000000-0000-4000-8000-000000000006"
T1 = "00000000-0000-4000-8000-000000000007"
T2 = "00000000-0000-4000-8000-000000000008"
R1 = "00000000-0000-4000-8000-000000000009"
R2 = "00000000-0000-4000-8000-000000000010"
SNAP = "00000000-0000-4000-8000-000000000011"
REQUEST = request_uuid(ISSUE_NUMBER, 6559266553)
REPO = "leandrosilveiradepaula/crm-infodive"
START = "a" * 40
CANDIDATE = "b" * 40
MERGE = "c" * 40
POLICY = "d" * 64
TEXT = "Autorizo corrigir a issue real #209 no CRM, somente Preview."
CREATED = "2026-11-01T14:27:01+00:00"
BASE = "preview/crm209-delivery-v4"
BRANCH = "factory/journey-" + JID
URL = "https://crm-infodive-example.vercel.app"


def fixture():
    digest = hashlib.sha256(TEXT.encode()).hexdigest()
    bind = {
        "journey_id": JID, "project_id": PID, "request_id": REQUEST,
        "repository": REPO, "source_repository": REPO,
        "source_commit": START, "policy_digest": POLICY,
        "policy_version": 4, "binding_version": 2, "execution_generation": 19,
        "release_base_ref": "main", "integration_branch": BRANCH,
        "preview_base_ref": BASE,
    }
    merge = {
        "repository": REPO, "candidate_commit": CANDIDATE, "head_sha": CANDIDATE,
        "head_ref": BRANCH, "base_ref": BASE, "merge_sha": MERGE,
        "merged": True, "environment": "preview",
        "production_released": False, "production_release_completed": False,
        "pr_number": "212", "preview_url": URL, "verifier_run_id": "41951864064",
    }
    def row(**kwargs):
        return kwargs
    data = {
        "factory_projects": [row(id=PID, project_key="crm-infodive",
            project_kind="existing", is_active=True, repository=REPO,
            manifest={"preview": {"required": True, "provider": "vercel"}})],
        "factory_journeys": [row(
            id=JID, project_id=PID, request_id=REQUEST, request_source="github-owner",
            auth_actor_ref="github-owner", auth_event_id="6559266553",
            request_digest=digest, request_snapshot={
                "text": TEXT, "digest": digest, "source": "github-owner",
                "authorization_event_id": "6559266553",
                "control_issue_repository": FACTORY_REPO, "control_issue_number": ISSUE_NUMBER,
            },
            issue_repository=FACTORY_REPO, issue_number=ISSUE_NUMBER,
            state="preview_verified", execution_generation=19,
            project_policy_version=4, policy_digest=POLICY, binding=bind,
            binding_version=2, source_commit=START, candidate_commit=CANDIDATE,
            production_release_sha=None, created_at=CREATED,
        )],
        "factory_audit_events": [
            row(id=1, project_id=PID, task_id=None, run_id=None,
                event_type="journey.intake_accepted", actor_type="human",
                actor_ref="github-owner", created_at=CREATED,
                payload={"state": "awaiting_source", "source": "github-owner",
                         "journey_id": JID, "request_id": REQUEST}),
            row(id=2, project_id=PID, task_id=ROOT, run_id=SOURCE,
                event_type="journey.source_bound", actor_type="system",
                actor_ref="journey-binder", created_at="2026-11-01T14:27:29+00:00",
                payload={"journey_id": JID, "request_id": REQUEST, "source_commit": START,
                         "preview_base_ref": BASE, "binding_digest": "f" * 64}),
            row(id=3, project_id=PID, task_id=ROOT, run_id=RELEASE,
                event_type="change_set.nonproduction_merge.observed", actor_type="system",
                actor_ref="nonproduction-release-observer", payload=merge),
        ],
        "factory_project_execution_controls": [
            row(project_id=PID, state="running", generation=19)],
        "factory_change_sets": [row(
            id=CS, project_id=PID, root_task_id=ROOT, release_run_id=RELEASE,
            journey_id=JID, status="completed", source_commit=START,
            candidate_commit=CANDIDATE, integration_branch=BRANCH,
            metadata={"integration_epoch_receipt": {
                "generation": 19, "project_id": PID, "candidate_commit": CANDIDATE},
                "nonproduction_integration": merge},
        )],
        "factory_tasks": [
            row(id=ROOT, project_id=PID, parent_task_id=None,
                journey_id=JID, status="integrated", risk={}),
            row(id=T1, project_id=PID, parent_task_id=ROOT,
                journey_id=JID, status="integrated", risk={}),
            row(id=T2, project_id=PID, parent_task_id=ROOT,
                journey_id=JID, status="integrated", risk={}),
        ],
        "factory_runs": [
            row(id=SOURCE, project_id=PID, task_id=ROOT, status="failed"),
            row(id=RELEASE, project_id=PID, task_id=ROOT,
                status="integrated", candidate_commit=CANDIDATE,
                branch_name=BRANCH, metadata={
                    "change_set_id": CS, "nonproduction_integration": merge}),
            row(id=R1, project_id=PID, task_id=T1, status="completed"),
            row(id=R2, project_id=PID, task_id=T2, status="completed"),
        ],
        "factory_change_set_work_units": [
            row(id="unit-1", change_set_id=CS, task_id=T1, run_id=R1,
                status="integrated", output_commit="1" * 40,
                changed_files=["src/a.ts"], created_at="2026-11-02T10:00:00+00:00"),
            row(id="unit-2", change_set_id=CS, task_id=T2, run_id=R2,
                status="integrated", output_commit="2" * 40,
                changed_files=["src/b.ts"], created_at="2026-11-03T10:00:00+00:00"),
        ],
        "factory_tool_usage": [
            row(id=1, run_id=SOURCE, operation="create_pr",
                metadata={"head_sha": "1" * 40, "pr": 212, "change_set_id": CS},
                created_at="2026-11-02T11:00:00+00:00"),
            row(id=2, run_id=RELEASE, operation="create_pr",
                metadata={"head_sha": CANDIDATE, "pr": 212, "change_set_id": CS},
                created_at="2026-11-03T11:00:00+00:00"),
            row(id=3, run_id=RELEASE, operation="verified_preview_awaiting_human_merge",
                metadata={"pr": 212, "head_sha": CANDIDATE, "preview_url": URL}),
            row(id=4, run_id=RELEASE, operation="nonproduction_merge_observed",
                metadata=merge),
        ],
        "factory_evaluations": [
            row(id="eval-1", run_id=RELEASE, eval_type="github_ci",
                status="success", baseline_ref=CANDIDATE,
                result={}, created_at="2026-11-04T12:00:00+00:00"),
            row(id="eval-2", run_id=RELEASE, eval_type="quality_gate",
                status="success", baseline_ref=CANDIDATE,
                result={"passed": True}, created_at="2026-11-04T12:01:00+00:00"),
            row(id="eval-3", run_id=RELEASE, eval_type="browser_e2e",
                status="success", baseline_ref=URL,
                result={}, created_at="2026-11-04T12:02:00+00:00"),
        ],
        "factory_specialist_lane_jobs": [
            row(id="lane-1", run_id=RELEASE, role="qa", required=True,
                status="passed", candidate_commit=CANDIDATE),
            row(id="lane-2", run_id=RELEASE, role="security", required=True,
                status="passed", candidate_commit=CANDIDATE),
            row(id="lane-3", run_id=RELEASE, role="operations", required=True,
                status="passed", candidate_commit=CANDIDATE),
        ],
        "factory_deployments": [
            row(id="deploy", run_id=RELEASE, environment="preview",
                status="success", metadata={
                    "candidate_commit": CANDIDATE, "preview_url": URL}),
        ],
        "factory_release_reports": [
            row(id="report", run_id=RELEASE, status="blocked",
                candidate_commit=CANDIDATE, created_at="2026-11-05T02:30:00+00:00",
                report={"release_state": "nonproduction_integrated",
                        "blockers": ["production requires separate gate"]}),
        ],
    }
    return data


class FrozenReader:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def _get(self, path, *, limit):
        self.calls.append((path, limit))
        table, query = path.split("?", 1)
        query_args = parse_qs(query)
        found = self.data[table]
        for key, val in query_args.items():
            if key in {"select", "order", "limit"}:
                continue
            match = val[0]
            if match.startswith("eq."):
                v = match[3:]
                found = [x for x in found if str(x.get(key)).lower() == v.lower()]
            elif match.startswith("gte."):
                found = [x for x in found
                         if not x.get(key) or x[key] >= match[4:]]
            elif match.startswith("in.(") and match.endswith(")"):
                allowed = set(match[4:-1].split(","))
                found = [x for x in found if str(x.get(key)) in allowed]
            else:
                raise AssertionError("invalid GET filter " + key)
        if "order" in query_args:
            key = query_args["order"][0].split(",")[0].split(".")[0]
            found = sorted(found, key=lambda x: x.get(key, 0))
            if query_args["order"][0].startswith(key + ".desc"):
                found.reverse()
        return copy.deepcopy(found[:limit])

    def _verified_nonproduction_integration(self, **kwargs):
        return True


class GitHub:
    def __init__(self, repository):
        self.repository = repository
        self.comment = {
            "id": 6559266553, "issue_url":
                "https://api.github.com/repos/" + FACTORY_REPO + "/issues/1055",
            "author_association": "OWNER",
            "user": {"id": OWNER_ID, "login": OWNER_LOGIN},
            "body": "/factory-start crm-infodive\n" + TEXT,
        }
        self.pr = GitHubPullRequest(
            number=212, head_sha=CANDIDATE, html_url="https://github.com/",
            merged=True, merge_commit_sha=MERGE, state="closed",
            head_ref=BRANCH, base_ref=BASE, head_repository=REPO, draft=False,
        )

    def _call(self, method, path, *, query=None):
        assert method == "GET", method
        if path.endswith("/issues/comments/6559266553"):
            return copy.deepcopy(self.comment)
        if path.endswith("/actions/runs/41951864064"):
            return {"id": 41951864064, "status": "completed",
                    "conclusion": "success"}
        if path.endswith("/actions/runs/41951864064/jobs"):
            return {"total_count": 1, "jobs": [
                {"name": "browser-evidence", "status": "completed",
                 "conclusion": "success"}]}
        raise AssertionError("unrecognized GET " + path)

    def get_pull_request(self, number):
        assert number == 212
        return self.pr

    def get_ci_state(self, number):
        assert number == 212
        return CIState.SUCCESS


def run(data=None, factory=None, crm=None):
    reader = FrozenReader(data if data is not None else fixture())
    factory = factory or GitHub(FACTORY_REPO)
    crm = crm or GitHub(REPO)
    with patch(
        "ai_product_factory.native_v2_journey_audit.verify_copied_work_unit_waves",
        return_value=True,
    ) as waves:
        proof = audit_existing_native_v2(
            reader=reader, project_key="crm-infodive", journey_id=JID,
            github_factory=lambda repository: (
                factory if repository == FACTORY_REPO else crm
            ),
        )
        assert waves.called
    assert all("/rpc/" not in path for path, _ in reader.calls)
    return proof


class NativeV2AuditTests(unittest.TestCase):
    def test_existing_journey_is_typed_and_production_remains_blocked(self):
        proof = run()
        self.assertEqual(proof["status"], "integrated_nonproduction")
        self.assertEqual(proof["highest_verified"], "awaiting_release")
        self.assertEqual(proof["verified_work_units"], 2)
        self.assertIs(proof["production_released"], False)
        self.assertIs(proof["product_ready"], False)
        self.assertEqual(proof["paid_calls"], 0)
        self.assertEqual(proof["writes"], 0)

    def test_owner_comment_and_intake_fail_closed(self):
        for change in (
            lambda d, f: d["factory_journeys"][0].update(auth_event_id="6559266554"),
            lambda d, f: d["factory_journeys"][0].update(request_digest="0" * 64),
            lambda d, f: d["factory_journeys"][0]["request_snapshot"].update(text="fake"),
            lambda d, f: d["factory_journeys"][0].update(request_id=JID),
            lambda d, f: d["factory_journeys"][0].update(issue_number=713),
            lambda d, f: d["factory_audit_events"][0]["payload"].update(request_id=JID),
            lambda d, f: d["factory_audit_events"][0].update(actor_ref="system"),
            lambda d, f: f.comment["user"].update(id=1),
            lambda d, f: f.comment.update(body="/factory-start other\n" + TEXT),
            lambda d, f: f.comment.update(author_association="NONE"),
        ):
            d, factory = fixture(), GitHub(FACTORY_REPO)
            change(d, factory)
            with self.subTest(mutation=repr(change)), self.assertRaises(EvidenceBlocked):
                run(d, factory=factory)

    def test_lineage_and_release_identity_fail_closed(self):
        for table, index, field, value in (
            ("factory_journeys", 0, "state", "executing"),
            ("factory_journeys", 0, "production_release_sha", MERGE),
            ("factory_project_execution_controls", 0, "generation", 20),
            ("factory_change_sets", 0, "status", "ci_pending"),
            ("factory_tasks", 0, "status", "queued_execution"),
            ("factory_tasks", 1, "parent_task_id", T2),
            ("factory_tasks", 1, "journey_id", ROOT),
            ("factory_runs", 1, "status", "awaiting_release"),
            ("factory_runs", 2, "task_id", T2),
            ("factory_change_set_work_units", 0, "status", "queued"),
            ("factory_specialist_lane_jobs", 0, "status", "failed"),
            ("factory_deployments", 0, "status", "pending"),
            ("factory_release_reports", 0, "status", "ready_for_human_release"),
            ("factory_evaluations", 0, "baseline_ref", START),
            ("factory_evaluations", 1, "status", "failed"),
            ("factory_evaluations", 2, "status", "failed"),
            ("factory_audit_events", 2, "actor_ref", "other"),
        ):
            d = fixture()
            d[table][index][field] = value
            with self.subTest(table=table, field=field), self.assertRaises(EvidenceBlocked):
                run(d)

    def test_immutable_bindings_and_merged_pr_fail_closed(self):
        for key, value in (
            ("source_commit", MERGE), ("policy_digest", "0" * 64),
            ("execution_generation", 20), ("preview_base_ref", "main"),
            ("integration_branch", "factory/other"),
        ):
            d = fixture()
            d["factory_journeys"][0]["binding"][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceBlocked):
                run(d)
        for attr, val in (
            ("merged", False), ("base_ref", "main"),
            ("head_sha", START), ("merge_commit_sha", START), ("draft", True),
        ):
            crm = GitHub(REPO)
            crm.pr = GitHubPullRequest(
                **{**crm.pr.__dict__, attr: val}
            )
            with self.subTest(attr=attr), self.assertRaises(EvidenceBlocked):
                run(crm=crm)

    def test_negative_paths(self):
        for paths in ([], ["src/a.ts", "src/a.ts"], ["/tmp/a.ts"],
                      ["a/../b.ts"], [".."], ["x\\y.ts"]):
            self.assertFalse(safe_paths(paths))

    def test_exact_owner_dispatch_and_comment(self):
        env = {
            "GITHUB_REPOSITORY": FACTORY_REPO, "GITHUB_REF": "refs/heads/main",
            "GITHUB_ACTOR": OWNER_LOGIN, "GITHUB_EVENT_NAME": "issue_comment",
        }
        event = {
            "action": "created", "sender": {"id": OWNER_ID, "login": OWNER_LOGIN},
            "issue": {"number": 713}, "comment": {
                "author_association": "OWNER",
                "user": {"id": OWNER_ID, "login": OWNER_LOGIN},
                "body": "/factory-v2-journey-audit crm-infodive " + JID,
            },
        }
        self.assertEqual(resolve_target(event=event, env=env), ("crm-infodive", JID))
        for mut in (
            lambda e, v: e["comment"].update(author_association="NONE"),
            lambda e, v: e["sender"].update(id=1),
            lambda e, v: e["issue"].update(number=1055),
            lambda e, v: e["comment"].update(body="/factory-wake"),
            lambda e, v: v.update(GITHUB_REF="refs/heads/feature"),
        ):
            e, v = copy.deepcopy(event), dict(env)
            mut(e, v)
            with self.subTest(mutation=repr(mut)), self.assertRaises(EvidenceBlocked):
                resolve_target(event=e, env=v)


if __name__ == "__main__":
    unittest.main()
