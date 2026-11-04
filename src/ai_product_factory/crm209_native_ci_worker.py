"""Single, exact, no-model CRM209 native repair through the existing Change Set builder.

The production SQL migration and separate human approval are prerequisites.
This helper has no generic retry, dispatch, model, merge or release interface.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .change_set_store import SupabaseChangeSetStore
from .change_set_worker import ChangeSetBuilderWorker
from .execution_worker import DirectExecutionItem, ImplementationArtifact
from .github_rest import GitHubRestAdapter
from .project_github_access import SupabaseProjectGitHubAccessStore
from .supabase_server import resolve_supabase_server_config

PROJECT = "crm-infodive"
REPO = "leandrosilveiradepaula/crm-infodive"
REQUEST = "ca53e605-b132-4937-aed3-f907cea2e221"
CS = "3f09952e-0384-46ee-97aa-a46c89346678"
SHA = "e5eb59c1a56b0c922a5e0d1e956e8c442dff152b"
GENERATION = 19
BRANCH = "factory/cs-3f09952e/ci-repair-4"
SCOPE = ("src/services/ContractService.ts", "test/contract-access.test.ts")
_CLAIM = "factory_claim_crm209_native_ci_once"
_ASSERT = "factory_assert_crm209_native_ci_claim"
_RESUME = "factory_resume_crm209_exhausted_native_ci_once"


class PaidModelForbidden:
    def produce(self, item: DirectExecutionItem) -> ImplementationArtifact:
        raise PermissionError("CRM209 native CI recovery refuses ALL paid model calls")


@dataclass(frozen=True)
class NativeClaim:
    run_id: str
    task_id: str
    work_unit_id: str
    worker_id: str


def _rpc(name: str, payload: dict) -> dict:
    cfg = resolve_supabase_server_config()
    req = urllib.request.Request(
        cfg.url + "/rest/v1/rpc/" + name,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={**cfg.headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(32768)
            if response.read(1):
                raise RuntimeError("CRM209 native receipt exceeded verified limit")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            detail = exc.read(4096)
            if b"PGRST202" in detail:
                return {"status": "blocked_migration_not_applied"}
        raise RuntimeError(f"CRM209 native Control Plane RPC {name} unavailable ({exc.code})") from None
    data = json.loads(raw) if raw else None
    if not isinstance(data, dict):
        raise RuntimeError("CRM209 native RPC returned invalid receipt")
    return data


def _idle(row: dict) -> bool:
    if row.get("status") == "blocked_migration_not_applied":
        return True
    return (row.get("status") == "idle"
            and row.get("requeued", row.get("claimed")) is False
            and row.get("paid_model_calls") == 0
            and row.get("release_authorized") is False)


def _authoritative_claim(row: dict, worker_id: str) -> NativeClaim:
    if (row.get("status") != "claimed"
        or row.get("claimed") is not True
        or row.get("paid_model_calls") != 0
        or row.get("model_calls_allowed") is not False
        or row.get("release_authorized") is not False
        or row.get("repository") != REPO
        or row.get("project_key") != PROJECT
        or row.get("change_set_id") != CS
        or row.get("candidate_commit") != SHA
        or row.get("branch") != BRANCH
        or row.get("wave") != 5
        or row.get("execution_generation") != GENERATION):
        raise PermissionError("CRM209 native Control Plane claim mismatch")
    import uuid
    for key in ("run_id", "task_id", "work_unit_id"):
        try:
            uuid.UUID(row[key])
        except (TypeError, KeyError, ValueError, AttributeError):
            raise PermissionError("CRM209 native claim lacks a UUID") from None
    return NativeClaim(row["run_id"], row["task_id"], row["work_unit_id"], worker_id)


class NativeCheckpointGitHub:
    """Stop any repository write when lease, status, epoch or scope changes."""
    WRITE_METHODS = frozenset({
        "commit_files", "create_issue", "create_pull_request",
        "create_branch", "create_branch_at_sha", "ensure_branch_at_sha",
        "update_file", "open_pull_request", "dispatch_workflow",
        "create_ref", "update_ref", "post_comment", "create_review",
        "close_issue",
    })

    def __init__(self, github: GitHubRestAdapter, checkpoint: Callable[[], None]):
        self._github = github
        self._checkpoint = checkpoint

    def __getattr__(self, name: str):
        attr = getattr(self._github, name)
        if name not in self.WRITE_METHODS or not callable(attr):
            return attr

        def verified_write(*args, **kwargs):
            self._checkpoint()
            return attr(*args, **kwargs)
        return verified_write


def run_once(*, worker_id: str, rpc: Callable[[str, dict], dict] = _rpc,
             github_factory: Callable[..., GitHubRestAdapter] = GitHubRestAdapter,
             store_factory: Callable[[], SupabaseChangeSetStore] = SupabaseChangeSetStore,
             builder_factory: Callable[..., ChangeSetBuilderWorker] = ChangeSetBuilderWorker,
             access_factory: Callable[[], SupabaseProjectGitHubAccessStore] = SupabaseProjectGitHubAccessStore,
             resume: bool = True) -> dict:
    if not isinstance(worker_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{8,100}", worker_id) is None:
        raise ValueError("invalid CRM209 native worker ID")
    # An explicit no-model flag is the only admission permission.
    if os.getenv("FACTORY_CRM209_NATIVE_ENABLED") != "true":
        return {"status": "disabled", "claimed": False, "paid_model_calls": 0,
                "release_authorized": False}
    if not os.getenv("FACTORY_GITHUB_TOKEN", "").strip():
        raise PermissionError("CRM209 native cross-repo token is unavailable")
    access_factory().require_capabilities(
        PROJECT, ("contents_write", "issues_write", "pull_requests_write")
    )
    github = github_factory(repository=REPO)
    # The database atomically resumes exhausted and claims the native Work Unit.
    # A separate resume call would briefly expose a queued paid Direct task.
    if resume is not True:
        raise ValueError("CRM209 native claim must always be atomic")
    # Re-verify the frozen GitHub candidate BEFORE claiming a lease.
    if github.get_branch_sha("factory/journey-bb14e150-2c7e-423b-8e5d-e211dab6225c") != SHA:
        raise PermissionError("CRM209 native PR candidate has changed")
    pr = github.get_pull_request(212)
    if (pr.number != 212 or pr.head_sha != SHA or pr.state != "open"
        or pr.merged or bool(pr.draft)
        or pr.head_ref != "factory/journey-bb14e150-2c7e-423b-8e5d-e211dab6225c"
        or pr.base_ref != "preview/crm209-delivery-v4"
        or pr.head_repository != REPO):
        raise PermissionError("CRM209 native PR origin, SHA or Preview base drifted")

    row = rpc(_CLAIM, {
        "p_worker_id": worker_id,
        "p_expected_candidate_commit": SHA,
        "p_expected_generation": GENERATION,
        "p_expected_request_id": REQUEST,
    })
    if _idle(row):
        return {"status": row["status"], "claimed": False,
                "paid_model_calls": 0, "release_authorized": False}
    claim = _authoritative_claim(row, worker_id)

    def checkpoint():
        receipt = rpc(_ASSERT, {
            "p_run_id": claim.run_id, "p_worker_id": worker_id,
            "p_candidate_commit": SHA, "p_generation": GENERATION,
        })
        if (receipt.get("status") != "verified"
            or receipt.get("run_id") != claim.run_id
            or receipt.get("model_calls_allowed") is not False
            or receipt.get("release_authorized") is not False):
            raise PermissionError("CRM209 native lease or epoch revoked")

    item = DirectExecutionItem(
        run_id=claim.run_id, task_id=claim.task_id, project_key=PROJECT,
        repository=REPO, issue_number=None, title=row["title"],
        description=row["description"], branch=BRANCH,
        change_set_id=CS, work_unit_id=claim.work_unit_id, wave=5,
    )
    store = store_factory()
    builder = builder_factory(
        github=NativeCheckpointGitHub(github, checkpoint), store=store,
        producer=PaidModelForbidden(), execution_route="direct",
    )
    try:
        checkpoint()
        result = builder.execute(item)
        if (result.run_id != claim.run_id
            or result.work_unit_id != claim.work_unit_id
            or result.change_set_id != CS or result.branch != BRANCH
            or not re.fullmatch(r"[a-f0-9]{40}", result.output_commit)
            or set(result.changed_files) != set(SCOPE)):
            raise PermissionError("CRM209 native implementation receipt mismatch")
        return {"status": "work_unit_completed", "claimed": True,
                "run_id":claim.run_id, "work_unit_id":claim.work_unit_id,
                "output_commit":result.output_commit, "paid_model_calls": 0,
                "release_authorized": False}
    except Exception as exc:
        # The builder itself settles preflight failures in the Control Plane.
        # A post-claim checkpoint error occurs before execution, so explicitly
        # block that same new Work Unit rather than silently leaking a lease.
        try:
            store.block_work_unit(
                run_id=claim.run_id,
                reason=("Native deterministic CI worker: "
                        + type(exc).__name__ + ": " + str(exc))[:1000],
                blocker_type="implementation_preflight_error",
            )
        except Exception:
            pass  # Preserve the ORIGINAL failure; recovery still fail-closed.
        raise
