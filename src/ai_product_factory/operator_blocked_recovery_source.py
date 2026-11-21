"""Evidence-only access to a previously authenticated operator SQL repair."""
from __future__ import annotations

import re
from typing import Callable
from urllib.parse import quote
from uuid import UUID

from .candidate_source_evidence import _bounded_excerpt
from .source_scope_admission import SourceScopeBlocked
from .work_unit_context import redact_repository_text

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_SQL = re.compile(r"supabase/migrations/[0-9]{14}_[a-z][a-z0-9_]*\.sql\Z")
_CODE = re.compile(r"[a-z][a-z0-9_]{2,80}\Z")
_DENIED = "operator_recovery_lineage_unverified"


def _uuid(raw: object) -> str:
    if not isinstance(raw, str):
        raise SourceScopeBlocked(_DENIED)
    try:
        if str(UUID(raw)) != raw:
            raise ValueError("invalid")
    except ValueError as exc:
        raise SourceScopeBlocked(_DENIED) from exc
    return raw


def _one(get: Callable[[str], object], table: str, field: str,
         ident: str, columns: str) -> dict:
    if not re.fullmatch(r"[a-z_]+", table + field):
        raise SourceScopeBlocked(_DENIED)
    try:
        rows = get(
            table + "?select=" + columns + "&" + field + "=eq."
            + quote(ident, safe="") + "&limit=2"
        )
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise SourceScopeBlocked(_DENIED) from exc
    if (not isinstance(rows, list) or len(rows) != 1
            or not isinstance(rows[0], dict) or rows[0].get(field) != ident):
        raise SourceScopeBlocked(_DENIED)
    return rows[0]


def _command(get: Callable[[str], object], pid: str, command_id: str) -> dict:
    try:
        rows = get(
            "factory_project_execution_commands?"
            "select=project_id,command_id,command,actor_id,expected_version,result"
            "&project_id=eq." + quote(pid, safe="")
            + "&command_id=eq." + quote(command_id, safe="") + "&limit=2"
        )
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise SourceScopeBlocked(_DENIED) from exc
    if (not isinstance(rows, list) or len(rows) != 1
            or not isinstance(rows[0], dict)
            or rows[0].get("project_id") != pid
            or rows[0].get("command_id") != command_id):
        raise SourceScopeBlocked(_DENIED)
    return rows[0]


def inspect_operator_sql_recovery(*, project: dict, context: dict,
                                  run_id: str, get: Callable[[str], object],
                                  github: object) -> dict:
    """Prove immutable operator/run/repair lineage before any GitHub reads.

    Source evidence authorizes planning limited to a previous SQL finding;
    never reopens the old Change Set, creates a Start, deploys or applies SQL.
    """
    pid = _uuid(project.get("id"))
    rid = _uuid(run_id)
    repo = project.get("repository")
    manifest = project.get("manifest")
    if (project.get("project_kind") != "greenfield"
            or not isinstance(repo, str) or not _REPO.fullmatch(repo)
            or getattr(github, "repository", None) != repo
            or not isinstance(context, dict)
            or not isinstance(manifest, dict)
            or manifest.get("source") != "factory-console"
            or manifest.get("onboarding_mode") != "greenfield"
            or not isinstance(manifest.get("bootstrap_request_id"), str)):
        raise SourceScopeBlocked(_DENIED)

    run = _one(get, "factory_runs", "id", rid,
               "id,task_id,status,execution_route,metadata")
    md = run.get("metadata")
    if (run.get("status") != "running"
            or run.get("execution_route") is not None
            or not isinstance(md, dict)
            or md.get("source") != "operator-blocked-work-recovery"
            or md.get("stages") != ["reconciliation", "gap_analysis", "planning"]):
        raise SourceScopeBlocked(_DENIED)
    task_id = _uuid(run.get("task_id"))
    command_id = _uuid(md.get("recovery_request_id"))
    source_id = _uuid(md.get("recovery_source_run_id"))
    job_id = _uuid(md.get("repair_job_id"))
    cs_id = _uuid(md.get("terminal_change_set_id"))

    request = _one(
        get, "factory_blocked_work_recovery_requests", "command_id", command_id,
        "id,project_id,command_id,source_task_id,source_run_id,repair_job_id,"
        "continuation_task_id,continuation_run_id,status,execution_generation",
    )
    request_id = _uuid(request.get("id"))
    original_run = _uuid(request.get("continuation_run_id"))
    if (request.get("project_id") != pid
            or request.get("source_run_id") != source_id
            or request.get("repair_job_id") != job_id
            or request.get("continuation_task_id") != task_id):
        raise SourceScopeBlocked(_DENIED)
    if "retry_of" in md:
        if request.get("status") != "blocked":
            raise SourceScopeBlocked(_DENIED)
        first = _one(get, "factory_runs", "id", original_run,
                     "id,task_id,status,last_error,metadata")
        if (first.get("task_id") != task_id or first.get("status") != "failed"
                or first.get("last_error") not in (
                    "reconciliation_context_preflight_failed",
                    "reconciliation_greenfield_owner_continuation_required")
                or not isinstance(first.get("metadata"), dict)
                or first["metadata"].get("source") != "operator-blocked-work-recovery"):
            raise SourceScopeBlocked(_DENIED)
        if md.get("retry_of") == original_run:
            if md.get("retry_source_generation") != str(request.get("execution_generation")):
                raise SourceScopeBlocked(_DENIED)
        else:
            # Exactly one additional retry for the original retry's source
            # authentication failure. This is not an unbounded replay.
            prior_id = _uuid(md.get("retry_of"))
            previous = _one(get, "factory_runs", "id", prior_id,
                            "id,task_id,status,last_error,metadata")
            pm = previous.get("metadata")
            if (previous.get("task_id") != task_id
                    or previous.get("status") != "failed"
                    or previous.get("last_error") != "reconciliation_context_preflight_failed"
                    or not isinstance(pm, dict)
                    or pm.get("retry_of") != original_run
                    or pm.get("retry_source_generation") != str(request.get("execution_generation"))
                    or pm.get("source") != "operator-blocked-work-recovery"
                    or md.get("retry_source_generation") is not None):
                raise SourceScopeBlocked(_DENIED)
    elif (rid != original_run
          or request.get("status") not in ("queued", "running")
          or md.get("execution_generation") != request.get("execution_generation")):
        raise SourceScopeBlocked(_DENIED)

    cmd = _command(get, pid, command_id)
    result = cmd.get("result")
    actor = _uuid(cmd.get("actor_id"))
    if (cmd.get("command") != "restart"
            or not isinstance(result, dict)
            or result.get("created") is not True
            or result.get("project_id") != pid
            or result.get("run_id") != original_run
            or result.get("task_id") != task_id
            or result.get("command") != "restart"
            or result.get("recovery_request_id") != request_id
            or result.get("state") != "running"):
        raise SourceScopeBlocked(_DENIED)
    op = _one(get, "factory_console_operators", "user_id", actor,
              "user_id,is_active")
    control = _one(get, "factory_project_execution_controls", "project_id",
                   pid, "project_id,state,version,generation")
    epoch = request.get("execution_generation")
    if (op.get("is_active") is not True
            or control.get("state") != "running"
            or type(epoch) is not int or epoch < 1
            or control.get("generation") != epoch
            or control.get("version") != cmd.get("expected_version")
            or result.get("generation") != epoch
            or result.get("version") != control.get("version")):
        raise SourceScopeBlocked(_DENIED)

    prior = _one(get, "factory_runs", "id", source_id,
                 "id,task_id,status,metadata,lease_owner,lease_expires_at")
    if (prior.get("status") != "blocked"
            or prior.get("task_id") != request.get("source_task_id")
            or prior.get("lease_owner") is not None
            or prior.get("lease_expires_at") is not None
            or not isinstance(prior.get("metadata"), dict)
            or prior["metadata"].get("change_set_id") != cs_id):
        raise SourceScopeBlocked(_DENIED)

    job = _one(get, "factory_repair_jobs", "id", job_id,
               "id,project_id,change_set_id,source_run_id,task_id,status,"
               "source_role,cycle,max_cycles,candidate_commit,finding,write_scopes")
    finding = job.get("finding")
    scopes = job.get("write_scopes")
    if (job.get("project_id") != pid or job.get("change_set_id") != cs_id
            or job.get("task_id") != request.get("source_task_id")
            or job.get("status") != "blocked"
            or job.get("source_role") != "security"
            or type(job.get("cycle")) is not int
            or type(job.get("max_cycles")) is not int
            or not 1 <= job["cycle"] < job["max_cycles"]
            or not isinstance(finding, dict)
            or finding.get("kind") != "database_security"
            or finding.get("severity") not in ("error", "critical")
            or not isinstance(finding.get("code"), str)
            or not _CODE.fullmatch(finding["code"])
            or not isinstance(finding.get("path"), str)
            or not _SQL.fullmatch(finding["path"])
            or scopes != [finding["path"]]
            or finding.get("scope_keys") != scopes
            or not isinstance(job.get("candidate_commit"), str)
            or not _SHA.fullmatch(job["candidate_commit"])):
        raise SourceScopeBlocked(_DENIED)
    path = finding["path"]
    task = _one(get, "factory_tasks", "id", task_id,
                "id,project_id,status,acceptance_criteria")
    if (task.get("project_id") != pid
            or task.get("status") not in ("queued", "running")
            or task.get("acceptance_criteria") != [
                {"finding": finding, "source_role": "security"}
            ]):
        raise SourceScopeBlocked(_DENIED)
    root = _one(get, "factory_runs", "id", _uuid(job.get("source_run_id")),
                "id,task_id,status")
    change_set = _one(get, "factory_change_sets", "id", cs_id,
                      "id,project_id,root_task_id,status,lease_owner,lease_expires_at")
    if (root.get("status") not in ("merged", "integrated", "completed")
            or change_set.get("project_id") != pid
            or change_set.get("root_task_id") != root.get("task_id")
            or change_set.get("status") != "completed"
            or change_set.get("lease_owner") is not None
            or change_set.get("lease_expires_at") is not None):
        raise SourceScopeBlocked(_DENIED)

    try:
        sha = github.get_branch_sha("main")
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise SourceScopeBlocked(_DENIED)
        comparison = github.compare_commits(job["candidate_commit"], sha)
        if (not isinstance(comparison, dict)
                or comparison.get("status") not in ("ahead", "identical")
                or comparison.get("behind_by") != 0):
            raise SourceScopeBlocked(_DENIED)
        governance = {}
        for name in ("README.md", "package.json"):
            doc = github.get_file_text(name, ref=sha)
            if (not isinstance(doc, str) or not doc.strip()
                    or len(doc.encode()) > 65536
                    or redact_repository_text(doc) != doc):
                raise SourceScopeBlocked(_DENIED)
            governance[name] = doc
        code = github.get_file_text(path, ref=sha)
        if (not isinstance(code, str) or not code.strip()
                or len(code.encode()) > 65536
                or redact_repository_text(code) != code):
            raise SourceScopeBlocked(_DENIED)
        excerpt, complete = _bounded_excerpt(code, 14000)
        if github.get_branch_sha("main") != sha:
            raise SourceScopeBlocked(_DENIED)
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise SourceScopeBlocked(_DENIED) from exc

    proof = {
        "status": "validated_operator_restart",
        "recovery_kind": "versioned_sql_security_repair",
        "run_id": rid, "project_id": pid,
        "command_id": command_id, "request_id": request_id,
        "source_run_id": source_id, "repair_job_id": job_id,
        "terminal_change_set_id": cs_id, "source_commit": sha,
        "scope_paths": list(scopes),
        "finding": {
            "kind": finding["kind"], "code": finding["code"],
            "severity": finding["severity"], "path": path,
        },
        "limitation": "Read-only lineage, not migration, merge or release authorization.",
    }
    candidate = {
        "repository": repo, "branch": "main", "sha": sha,
        "main_sha": sha, "verified_open_pr": None,
        "observed_from": "live_greenfield_operator_recovery_exact_sha",
        "governance": governance,
        "source_evidence": {
            "status": "bounded_source_inspected",
            "assessed_commit": sha,
            "request_source_paths": [path],
            "inspected_files": [{
                "path": path, "assessed_commit": sha, "content": excerpt,
                "complete": complete, "total_lines": code.count("\n") + 1,
            }],
            "missing_paths": [], "omitted_paths": [],
            "limitation": "Bounded exact-source excerpt only; no release evidence.",
        },
    }
    result = dict(context)
    facts = dict(result.get("current_state_facts") or {})
    facts["operator_recovery"] = proof
    facts["live_candidate"] = candidate
    result["current_state_facts"] = facts
    return result
