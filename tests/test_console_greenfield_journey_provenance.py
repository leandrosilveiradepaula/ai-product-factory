"""Fail-closed proof of atomic Console greenfield Start provenance.

The Factory must recognize its own durable greenfield intake, not invent a
Start from a queued run or a project creation event. All fixtures are offline;
no database mutation, GitHub call, or paid model is involved.
"""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ai_product_factory.autonomy_journey import evaluate_journey, STAGES
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader


PID = "00000000-0000-0000-0000-000000000001"
ROOT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"
DRAFT = "00000000-0000-0000-0000-000000000004"
OPERATOR = "00000000-0000-0000-0000-000000000005"
WHEN = "2026-10-15T14:24:57.341475+00:00"
CUTOFF = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)


def fixture():
    project = {
        "id": PID, "project_key": "example-greenfield",
        "project_kind": "greenfield", "repository": "example/workload",
        "is_active": True, "created_at": WHEN,
        "manifest": {
            "source": "factory-console", "onboarding_mode": "greenfield",
            "reconcile_first": False, "bootstrap_request_id": DRAFT,
            "bootstrap_operator_id": OPERATOR,
            "bootstrap_attachment_count": 0,
        },
    }
    run = {
        "id": ROOT, "task_id": TASK, "status": "completed",
        "created_at": WHEN, "candidate_commit": None,
        "metadata": {
            "source": "factory-console",
            "stages": ["discovery", "specification", "planning"],
        },
    }
    task = {
        "id": TASK, "project_id": PID, "parent_task_id": None,
        "external_key": "product-bootstrap-v1",
        "status": "completed", "created_at": WHEN,
    }
    receipts = [
        {
            "id": 860, "project_id": PID, "task_id": None, "run_id": None,
            "created_at": WHEN, "actor_type": "human", "actor_ref": "factory-console",
            "event_type": "project.intake.created",
            "payload": {"project_key": "example-greenfield", "project_kind": "greenfield"},
        },
        {
            "id": 861, "project_id": PID, "task_id": None, "run_id": None,
            "created_at": WHEN, "actor_type": "human", "actor_ref": "factory-console",
            "event_type": "project.attachments.finalized",
            "payload": {"draft_id": DRAFT, "count": 0},
        },
        {
            "id": 862, "project_id": PID, "task_id": None, "run_id": ROOT,
            "created_at": WHEN, "actor_type": "system", "actor_ref": "factory-console",
            "event_type": "project.bootstrap.enqueued", "payload": {"task_id": TASK},
        },
    ]
    stage_events = [
        {
            "id": 863 + index, "project_id": PID, "task_id": TASK,
            "run_id": ROOT, "created_at": WHEN, "actor_type": "system",
            "actor_ref": "product-worker", "event_type": "product.stage.persisted",
            "payload": {"stage": stage},
        }
        for index, stage in enumerate(("discovery", "specification", "planning"))
    ]
    start = {
        "command": "console_greenfield_intake", "actor_id": OPERATOR,
        "request_id": DRAFT, "attachment_count": 0,
        "bootstrap_task_id": TASK, "result": {"run_id": ROOT},
    }
    return project, run, task, receipts, stage_events, start


def evaluation(*, project=None, run=None, receipts=None, start=None, stage_events=None):
    p, r, _task, e, stage, st = fixture()
    return evaluate_journey(
        project=p if project is None else project,
        root_run_id=ROOT, start_command=st if start is None else start,
        runs=[r if run is None else run],
        events=(e if receipts is None else receipts) +
               (stage if stage_events is None else stage_events),
        change_sets=[], work_units=[], create_pr_receipts=[],
        deployments=[], release_reports=[], github=None,
        preview_required=True,
    )


class AtomicConsoleGreenfieldStartTests(unittest.TestCase):
    def test_real_atomic_start_reaches_only_verified_product_stages(self):
        report = evaluation()
        self.assertEqual(report.highest_verified, "planning")
        self.assertEqual(report.status, "in_progress")
        self.assertEqual(report.stages[STAGES.index("manual_start")].status, "verified")
        self.assertEqual(report.stages[STAGES.index("implementation")].status, "not_reached")
        self.assertFalse(report.as_json()["product_ready"])
        self.assertEqual(report.as_json()["paid_calls"], 0)
        self.assertEqual(report.as_json()["writes"], 0)

    def test_missing_reordered_or_forged_audit_receipts_never_start_a_journey(self):
        _, _, _, original, _, _ = fixture()
        for label, mutate in (
            ("missing human intake", lambda rows: rows.pop(0)),
            ("missing enqueue", lambda rows: rows.pop(2)),
            ("duplicate enqueue", lambda rows: rows.append(copy.deepcopy(rows[2]))),
            ("reordered pair", lambda rows: rows.reverse()),
            ("wrong actor", lambda rows: rows[0].update(actor_ref="unknown")),
            ("wrong actor type", lambda rows: rows[1].update(actor_type="system")),
            ("wrong audit project", lambda rows: rows[0].update(project_id="other-project")),
            ("wrong draft", lambda rows: rows[1]["payload"].update(draft_id=OPERATOR)),
            ("wrong attachment count", lambda rows: rows[1]["payload"].update(count=1)),
            ("wrong bootstrap task", lambda rows: rows[2]["payload"].update(task_id=OPERATOR)),
            ("wrong bootstrap run", lambda rows: rows[2].update(run_id=OPERATOR)),
            ("wrong receipt time", lambda rows: rows[1].update(created_at="2026-10-15T14:25:00+00:00")),
            ("wrong ID sequence", lambda rows: rows[2].update(id=850)),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                rows = copy.deepcopy(original)
                mutate(rows)
                evaluation(receipts=rows)

    def test_manifest_and_root_identity_fail_closed(self):
        for field, value in (
            ("bootstrap_request_id", OPERATOR),
            ("bootstrap_operator_id", DRAFT),
            ("bootstrap_attachment_count", 1),
            ("source", "unverified"),
            ("onboarding_mode", "existing"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                project = fixture()[0]
                project["manifest"][field] = value
                evaluation(project=project)
        for field, value in (
            ("task_id", OPERATOR), ("created_at", "2026-10-15T14:25:00+00:00"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                run = fixture()[1]
                if field == "task_id":
                    run[field] = value
                else:
                    # The reader, not the pure evaluator, checks run creation time.
                    run["metadata"]["source"] = "unverified"
                evaluation(run=run)
        self.assertRaises(ValueError, evaluation,
                          start=dict(fixture()[5], actor_id=""))

    def test_bounded_reader_accepts_exact_atomic_start_without_github(self):
        project, root, task, receipts, stages, _ = fixture()
        github = MagicMock()
        reader = SupabaseJourneyReader(
            url="https://example.supabase.co",
            secret_key="sb_secret_placeholder",
            github_factory=github,
        )
        observed_paths = []

        def one(table, query):
            if table == "factory_projects":
                return project
            if table == "factory_runs":
                return root
            if table == "factory_tasks":
                return task
            self.fail("unrecognized direct read: " + table)

        def get(path, *, limit):
            observed_paths.append(path)
            if path.startswith("factory_project_execution_commands?"):
                return []
            if path.startswith("factory_audit_events?") and (
                "project.continuation.requested" in path or
                "project.reconciliation.enqueued" in path
            ):
                return []
            if path.startswith("factory_audit_events?") and (
                "project.intake.created" in path
            ):
                return receipts
            if path.startswith("factory_audit_events?"):
                return receipts + stages
            if path.startswith("factory_project_attachments?"):
                return []
            if path.startswith("factory_tasks?"):
                return [task]
            if path.startswith(("factory_change_sets?", "factory_release_reports?")):
                return []
            self.fail("unrecognized GET: " + path)

        def many(table, *, cols, fk, ids, extra="", limit=301):
            if table == "factory_runs":
                return [root]
            return []

        with patch.object(reader, "_one", side_effect=one), \
             patch.object(reader, "_get", side_effect=get), \
             patch.object(reader, "_many_ids", side_effect=many):
            report = reader.read(project_key=project["project_key"],
                                 since=CUTOFF, run_id=ROOT)
        self.assertEqual(report.highest_verified, "planning")
        self.assertTrue(any("factory_project_attachments?" in p for p in observed_paths))
        self.assertTrue(any("project.intake.created" in p for p in observed_paths))
        github.assert_not_called()

    def test_reader_refuses_unsigned_or_incomplete_intake_and_wrong_requested_run(self):
        project, _, _, receipts, _, _ = fixture()
        reader = SupabaseJourneyReader(
            url="https://example.supabase.co", secret_key="sb_secret_placeholder",
        )
        with patch.object(reader, "_get", return_value=receipts):
            start = reader._console_greenfield_intake_start(project, ROOT, CUTOFF)
        self.assertEqual(start["result"]["run_id"], ROOT)
        self.assertEqual(start["request_id"], DRAFT)
        unbound = copy.deepcopy(project)
        del unbound["manifest"]["bootstrap_request_id"]
        self.assertIsNone(reader._console_greenfield_intake_start(unbound, ROOT, CUTOFF))
        with patch.object(reader, "_get", return_value=receipts):
            with self.assertRaisesRegex(RuntimeError, "explicit audit run differs"):
                reader._console_greenfield_intake_start(project, OPERATOR, CUTOFF)
            for case in ("missing_pair", "duplicate", "wrong_actor"):
                bad = copy.deepcopy(receipts)
                if case == "missing_pair":
                    bad.pop(0)
                elif case == "duplicate":
                    bad.append(copy.deepcopy(bad[2]))
                else:
                    bad[0]["actor_ref"] = "random-user"
                with self.subTest(case=case), patch.object(reader, "_get", return_value=bad):
                    with self.assertRaises(RuntimeError):
                        reader._console_greenfield_intake_start(project, ROOT, CUTOFF)
