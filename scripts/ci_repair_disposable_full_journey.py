"""Single-fixture, cross-layer CI recovery proof against disposable PostgreSQL 16.

Runs real Factory CI follow-up, SQL repair RPC, ChangeSetIntegrator crash
recovery, CI passed receipt and explicit Preview N/A -> awaiting_release.
Only external GitHub IO and specialist evidence persistence are simulated.
Do NOT use with a production database or a real GitHub token.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_factory.autonomous_github import AutonomousGitHubLoop, GitHubWorkSession
from ai_product_factory.change_set_integrator import ChangeSetIntegrator
from ai_product_factory.change_set_store import ChangeSetIntegrationItem
from ai_product_factory.ci_followup_queue import CIFollowupItem
from ai_product_factory.ci_repair_queue import SupabaseCIRepairQueue
from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubCheckFailure, GitHubIssue, GitHubPullRequest
from ai_product_factory.preview_policy import evaluate_preview_applicability
from ai_product_factory.project_followup_guard import ProjectFollowupPaused
from ai_product_factory.runtime_cli import run_ci_once

SOURCE = "8" * 40
OUTPUT = "7" * 40
REPAIRED = "9" * 40


def prove_full_journey(conn, setup, *, repository: str, branch: str):
    """No DDL, network, LLM, non-test project, or GitHub repository mutation."""
    project, root_task, source_run, change_set = setup(conn, sha=SOURCE)
    events: list[str] = []
    release_id = uuid.uuid4()

    class FakeGitHub:
        repository = repository
        branch_sha = SOURCE
        message = ""
        commits = 0
        issues = 0
        prs = 0
        phase = "failed"
        merged = False

        def get_branch_sha(self, ref):
            if ref == "main":
                return SOURCE
            if ref != branch:
                raise AssertionError("unexpected branch")
            return self.branch_sha

        def ensure_branch_at_sha(self, ref, sha):
            if self.get_branch_sha(ref) != sha:
                raise RuntimeError("branch moved before integration")

        def get_file_text(self, path, *, ref):
            assert path == "src/core.py" and ref in (OUTPUT, REPAIRED)
            return "fixed = True\n"

        def commit_files(self, ref, contents, *, message):
            assert ref == branch and self.branch_sha == SOURCE
            assert contents == {"src/core.py": "fixed = True\n"}
            self.branch_sha = REPAIRED
            self.message = message
            self.commits += 1
            events.append("github_commit")
            return REPAIRED

        def get_commit_provenance(self, sha):
            assert sha == REPAIRED
            return self.message, (SOURCE,)

        def verify_integration_commit_tree(self, *, parent_sha, candidate_sha, expected_paths):
            assert (parent_sha, candidate_sha, expected_paths) == (
                SOURCE, REPAIRED, ("src/core.py",)
            )
            events.append("exact_tree_recovered")

        def get_pull_request(self, number):
            assert number == 73
            return GitHubPullRequest(
                73, self.branch_sha, "https://example.invalid/pr/73",
                merged=self.merged, head_ref=branch, base_ref="main",
                head_repository=repository,
            )

        def get_issue(self, number):
            assert number == 7
            return GitHubIssue(7, "Fixture", "Offline-only", "https://example.invalid/7")

        def get_ci_state(self, number):
            assert number == 73
            return CIState.FAILURE if self.phase == "failed" else CIState.SUCCESS

        def get_failed_checks(self, number, *, expected_head_sha):
            assert number == 73 and expected_head_sha == SOURCE
            return (GitHubCheckFailure(
                "native-ci/tests", "failure",
                details_url="https://example.invalid/ci/123",
                summary="Verified exact-attempt test failure", failure_class="code",
            ),)

        def find_open_issue_containing(self, marker):
            assert str(change_set) in marker
            return None

        def create_issue(self, *, title, body):
            self.issues += 1
            return self.get_issue(7)

        def find_open_pull_request_containing(self, marker):
            assert str(change_set) in marker
            return None

        def create_pull_request(self, *, title, body, head, base):
            assert head == branch and base == "main"
            self.prs += 1
            return self.get_pull_request(73)

    github = FakeGitHub()

    class RealPostgresRepairQueue(SupabaseCIRepairQueue):
        def __init__(self):
            # No network or credential initialization. _rpc executes the
            # production SQL migrations against this disposable PG connection.
            pass

        def _rpc(self, name, payload):
            if name == "factory_enqueue_ci_repair":
                keys = ("p_source_run_id", "p_project_id", "p_change_set_id",
                        "p_repository", "p_pr_number", "p_branch",
                        "p_candidate_commit", "p_execution_generation",
                        "p_failure_class", "p_failures", "p_max_attempts")
                args = [json.dumps(payload[k]) if k == "p_failures" else payload[k]
                        for k in keys]
                response = conn.execute(
                    "select public.factory_enqueue_ci_repair("
                    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)", args,
                ).fetchone()[0]
                events.append("sql_repair_enqueued")
                return response
            if name == "factory_record_ci_repair_result":
                response = conn.execute(
                    "select public.factory_record_ci_repair_result(%s,%s,%s)",
                    (payload["p_release_run_id"],
                     payload["p_candidate_commit"], payload["p_status"]),
                ).fetchone()[0]
                if response.get("updated") and response.get("status") == "passed":
                    events.append("sql_ci_passed")
                return response
            raise AssertionError("unapproved RPC in offline journey: " + name)

    repairs = RealPostgresRepairQueue()

    def project_guard(item):
        state, generation = conn.execute(
            "select state,generation from public.factory_project_execution_controls "
            "where project_id=%s", (project,),
        ).fetchone()
        if state != "running" or generation != item.execution_generation:
            raise ProjectFollowupPaused("project_control_waiting")
        return generation

    class SqlDeliveryStore:
        def update_run_status(self, run_id, status, *, candidate_commit=None):
            conn.execute(
                "update public.factory_runs set status=%s where id=%s", (status, run_id)
            )
            events.append("run_" + status)

        def record_tool_usage(self, *, run_id, tool_family, operation, metadata):
            conn.execute(
                "insert into public.factory_tool_usage(run_id,operation,metadata) "
                "values (%s,%s,%s::jsonb)",
                (run_id, operation, json.dumps(metadata)),
            )

        def record_evaluation(self, **kwargs):
            events.append("evaluated_" + kwargs["eval_type"])

        def record_audit_event(self, **kwargs):
            events.append("audit_" + kwargs["event_type"])

    store = SqlDeliveryStore()

    class SqlSpecialists:
        def enqueue(self, run_id):
            observed = conn.execute(
                "select status from public.factory_ci_repair_requests "
                "where release_run_id=%s and repaired_commit=%s",
                (run_id, REPAIRED),
            ).fetchone()
            assert observed == ("passed",), "specialists reached before CI receipt"
            conn.execute(
                "update public.factory_runs set status='specialist_review_pending' "
                "where id=%s", (run_id,),
            )
            events.append("specialist_enqueued")
            return {"status": "specialist_review_pending"}

    class Traceability:
        def record_delivery_evidence(self, **kwargs):
            assert kwargs["evidence_type"] == "github_ci"
            events.append("ci_evidence_stored")

    class SqlIntegrationStore:
        fail_once = True

        def complete_integration(self, *, item, candidate_commit, changed_files):
            assert candidate_commit == REPAIRED
            assert changed_files == ("src/core.py",)
            if self.fail_once:
                self.fail_once = False
                events.append("crash_before_sql_integration")
                raise RuntimeError("simulated crash after exact GitHub commit")
            conn.execute(
                "update public.factory_change_set_work_units "
                "set status='integrated', changed_files=%s::jsonb where id=%s",
                (json.dumps(["src/core.py"]), repair["work_unit_id"]),
            )
            conn.execute(
                "update public.factory_change_sets "
                "set candidate_commit=%s,status='review_ready' where id=%s",
                (candidate_commit, change_set),
            )
            state = conn.execute(
                "select status from public.factory_ci_repair_requests where id=%s",
                (repair["repair_request_id"],),
            ).fetchone()
            assert state == ("integrated",), state
            events.append("sql_integration_recovered")
            return {
                "status": "review_ready", "change_set_id": str(change_set),
                "candidate_commit": candidate_commit,
                "current_wave": item.current_wave,
                "repair_jobs_integrated": 1,
            }

        def prepare_release(self, *, item, issue_number, issue_url,
                            pr_number, candidate_commit, branch):
            assert issue_number == 7 and pr_number == 73 and candidate_commit == REPAIRED
            metadata = {
                "source": "change-set", "change_set_id": str(change_set),
                "execution_generation": 3, "github_issue": {"number": 7},
            }
            conn.execute(
                "insert into public.factory_runs "
                "(id,task_id,status,candidate_commit,branch_name,metadata) "
                "values (%s,%s,'ci_pending',%s,%s,%s::jsonb)",
                (release_id, root_task, REPAIRED, branch, json.dumps(metadata)),
            )
            conn.execute(
                "update public.factory_change_sets "
                "set status='ci_pending',release_run_id=%s where id=%s",
                (release_id, change_set),
            )
            request = conn.execute(
                "select status,release_run_id,repaired_commit "
                "from public.factory_ci_repair_requests where id=%s",
                (repair["repair_request_id"],),
            ).fetchone()
            assert request == ("awaiting_ci", release_id, REPAIRED), request
            events.append("sql_ci_pending_repaired")
            return {"status": "ci_pending", "change_set_id": str(change_set),
                    "release_run_id": str(release_id)}

    def item(run, candidate):
        return CIFollowupItem(
            run_id=str(run), project_key="isolated", repository=repository,
            issue_number=7, branch=branch, pr_number=73,
            candidate_commit=candidate, human_gate_required=False,
            change_set_id=str(change_set), project_id=str(project),
            execution_generation=3, require_execution_generation=True,
        )

    # The actual runtime entrypoint calls the real SQL RPC and commits no
    # GitHub changes during the failed-CI handoff.
    from unittest.mock import MagicMock
    followups = MagicMock()
    followups.next_pending.return_value = item(source_run, SOURCE)
    with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=followups), \
         patch("ai_product_factory.runtime_cli.SupabaseCIRepairQueue", return_value=repairs), \
         patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=github), \
         patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore", return_value=store), \
         patch("ai_product_factory.runtime_cli._assert_project_followup", side_effect=project_guard):
        initial = run_ci_once()
    assert initial["status"] == "repair_pending", initial
    assert initial["failure_classes"] == ["code"]
    repair = initial["repair"]
    assert repair["attempt"] == 1 and repair["created"] is True
    assert github.commits == 0
    assert conn.execute(
        "select status from public.factory_change_sets where id=%s",
        (change_set,),
    ).fetchone() == ("building",)

    # GitHub timeout/replay cannot allocate a second work unit.
    replay = repairs.enqueue_failure(
        item=item(source_run, SOURCE),
        failures=(__import__(
            "ai_product_factory.ci_repair_queue", fromlist=["DurableCIFailure"]
        ).DurableCIFailure.from_github(github.get_failed_checks(
            73, expected_head_sha=SOURCE,
        )[0]),),
        max_attempts=3,
    )
    assert replay["created"] is False and replay["repair_request_id"] == repair["repair_request_id"]
    assert conn.execute(
        "select count(*) from public.factory_ci_repair_requests where change_set_id=%s",
        (change_set,),
    ).fetchone()[0] == 1

    wave = conn.execute(
        "select current_wave from public.factory_change_sets where id=%s", (change_set,),
    ).fetchone()[0]
    integration_item = ChangeSetIntegrationItem(
        change_set_id=str(change_set), project_key="isolated",
        repository=repository, source_commit=SOURCE,
        candidate_commit=SOURCE, integration_branch=branch,
        current_wave=wave, project_kind="platform",
        work_units=({
            "plan_task_key": "ci-repair", "base_commit": SOURCE,
            "output_commit": OUTPUT, "changed_files": ["src/core.py"],
        },),
    )
    integrator = ChangeSetIntegrator(github=github, store=SqlIntegrationStore())
    try:
        integrator.integrate(integration_item)
    except RuntimeError as error:
        assert str(error) == "simulated crash after exact GitHub commit", error
    else:
        raise AssertionError("crash was not simulated")
    assert github.commits == 1 and github.branch_sha == REPAIRED
    assert conn.execute(
        "select candidate_commit,status from public.factory_change_sets where id=%s",
        (change_set,),
    ).fetchone() == (SOURCE, "building")

    # New process: exactly same branch commit is recovered from parent/trailer,
    # full authorized tree and text, without writing a second commit.
    integration = integrator.integrate(integration_item)
    assert integration.status == "ci_pending", integration
    assert integration.candidate_commit == REPAIRED
    assert github.commits == 1 and github.prs == 1 and github.issues == 1
    assert conn.execute(
        "select status from public.factory_ci_repair_requests where id=%s",
        (repair["repair_request_id"],),
    ).fetchone() == ("awaiting_ci",)

    # Paused projects cannot turn a green external CI into specialist work.
    conn.execute(
        "update public.factory_project_execution_controls "
        "set state='paused' where project_id=%s", (project,),
    )
    followups.next_pending.return_value = item(release_id, REPAIRED)
    github.phase = "green"
    with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=followups), \
         patch("ai_product_factory.runtime_cli.SupabaseCIRepairQueue", return_value=repairs), \
         patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=github), \
         patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore", return_value=store), \
         patch("ai_product_factory.runtime_cli._assert_project_followup", side_effect=project_guard):
        paused = run_ci_once()
    assert paused["status"] == "project_control_waiting", paused
    assert conn.execute(
        "select status from public.factory_ci_repair_requests where id=%s",
        (repair["repair_request_id"],),
    ).fetchone() == ("awaiting_ci",)
    conn.execute(
        "update public.factory_project_execution_controls "
        "set state='running' where project_id=%s", (project,),
    )

    with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=followups), \
         patch("ai_product_factory.runtime_cli.SupabaseCIRepairQueue", return_value=repairs), \
         patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=github), \
         patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore", return_value=store), \
         patch("ai_product_factory.runtime_cli.SupabaseSpecialistLaneQueue", return_value=SqlSpecialists()), \
         patch("ai_product_factory.runtime_cli.SupabaseTraceabilityStore", return_value=Traceability()), \
         patch("ai_product_factory.runtime_cli._assert_project_followup", side_effect=project_guard):
        green = run_ci_once()
    assert green["status"] == "specialist_review_pending", green
    assert green["ci_repair_result"]["status"] == "passed"
    assert events.index("sql_ci_passed") < events.index("specialist_enqueued")
    assert conn.execute(
        "select status from public.factory_ci_repair_requests where id=%s",
        (repair["repair_request_id"],),
    ).fetchone() == ("passed",)
    assert conn.execute(
        "select status from public.factory_runs where id=%s",
        (release_id,),
    ).fetchone() == ("specialist_review_pending",)

    # Only explicit project policy can make Preview N/A. Evidence is durable
    # and the release remains human-gated; GitHub never receives a merge call.
    applicability = evaluate_preview_applicability(
        manifest={"preview": {"required_paths": ["apps/console/**"]}},
        changed_files=("src/core.py",),
    )
    assert applicability.required is False
    session = GitHubWorkSession(
        github.get_issue(7), branch, str(release_id), "", "",
        github.get_pull_request(73),
    )
    status = AutonomousGitHubLoop(github, store).finalize_preview_not_required(
        session, reason=applicability.reason, changed_files=("src/core.py",),
    )
    assert status == "awaiting_release"
    assert conn.execute(
        "select status from public.factory_runs where id=%s",
        (release_id,),
    ).fetchone() == ("awaiting_release",)
    evidence = conn.execute(
        "select metadata from public.factory_tool_usage "
        "where run_id=%s and operation='preview_not_required_awaiting_human_merge'",
        (release_id,),
    ).fetchone()[0]
    assert evidence["head_sha"] == REPAIRED
    assert evidence["changed_files"] == ["src/core.py"]
    assert not github.merged
    assert events.index("sql_ci_passed") < events.index("run_awaiting_release")
    print("CI_REPAIR_CROSS_LAYER_ISOLATED_PASS")
