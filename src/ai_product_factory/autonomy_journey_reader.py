"""Strict read-only adapters for fresh, operator-started autonomy journeys."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from .autonomy_journey import evaluate_journey, no_start_report, SHA
from .journey_candidate_provenance import (
    validate_reconciliation_receipt, verify_copied_work_units,
)
from .github_rest import GitHubRestAdapter
from .preview_policy import evaluate_preview_applicability
from .supabase_server import resolve_supabase_server_config

PROJECT_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{1,119}$")
MAX_PROJECT_TASKS = 300
MAX_PROJECT_EVENTS = 500

# These historical release receipts are emitted with project_id=NULL by the
# existing worker. They are safe only when also pinned to the exact Start
# descendant run and to a matching PR/SHA; other NULL-project audits are
# intentionally outside the accepted read surface.
GLOBAL_RELEASE_EVENTS = (
    "release.awaiting_human_merge",
    "release.preview_not_required",
    "release.human_merge_observed",
    "quality_gate.passed",
)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("expected UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("invalid UUID") from exc
    if str(parsed) != value:
        raise ValueError("noncanonical UUID")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected ISO UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include UTC timezone")
    return parsed.astimezone(timezone.utc)


def _utc_filter(instant: datetime) -> str:
    return quote(instant.isoformat(timespec="microseconds").replace("+00:00", "Z"),safe="")


def candidate_contains_work_units(github, candidate_sha: str, commits: set[str]) -> bool:
    """Verify every completed Work Unit commit belongs to the candidate ancestry.

    A SHA existing in the repository but absent from the proposed PR is not
    delivery evidence. The GitHub compare API is read-only and bounded.
    """
    if not isinstance(candidate_sha,str) or not SHA.fullmatch(candidate_sha):
        raise ValueError("candidate must be an exact commit SHA")
    if not isinstance(commits,set) or len(commits)>30 or not commits:
        raise ValueError("implementation commit inventory is missing or unbounded")
    for sha in sorted(commits):
        if not isinstance(sha,str) or not SHA.fullmatch(sha):
            raise ValueError("invalid Work Unit commit SHA")
        if not github.commit_exists(sha):
            return False
        if sha == candidate_sha:
            continue
        comparison=github.compare_commits(sha,candidate_sha)
        if (
            not isinstance(comparison,dict)
            or comparison.get("status") != "ahead"
            or type(comparison.get("ahead_by")) is not int
            or comparison["ahead_by"] < 1
            or type(comparison.get("behind_by")) is not int
            or comparison["behind_by"] != 0
        ):
            return False
    return True


class SupabaseJourneyReader:
    """Read a bounded lineage using only PostgREST GET and GitHub GET.

    No webhook, SQL RPC, model, CI dispatch, transaction, state update or
    release action is invoked. Unbounded/partial data fails closed.
    """
    def __init__(self, *, url: str | None = None, secret_key: str | None = None,
                 github_factory=GitHubRestAdapter):
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key)
        self.url=cfg.url
        self.headers=cfg.headers
        self.github_factory=github_factory

    def _get(self, path: str, *, limit: int) -> list[dict]:
        if not 1 <= limit <= 501:
            raise ValueError("invalid read-only inventory limit")
        separator="&" if "?" in path else "?"
        request=urllib.request.Request(
            self.url+"/rest/v1/"+path+separator+"limit="+str(limit),
            headers=self.headers,method="GET",
        )
        try:
            with urllib.request.urlopen(request,timeout=25) as response:
                body=response.read(768001)
        except urllib.error.HTTPError as exc:
            # Never print proxy response bodies: they may include internal data.
            raise RuntimeError("read-only Control Plane request failed: HTTP "+str(exc.code)) from exc
        if len(body)>768000:
            raise RuntimeError("Control Plane payload exceeded bounded size")
        try:
            items=json.loads(body.decode("utf-8"))
        except (ValueError,UnicodeDecodeError) as exc:
            raise RuntimeError("Control Plane returned invalid JSON") from exc
        if not isinstance(items,list) or len(items)>=limit or any(not isinstance(item,dict) for item in items):
            raise RuntimeError("Control Plane inventory is incomplete or malformed")
        return items

    def _one(self, table: str, query: str) -> dict | None:
        rows=self._get(table+"?"+query,limit=2)
        return rows[0] if rows else None

    def _many_ids(self, table: str, *, cols: str, fk: str, ids: set[str],
                  extra: str = "", limit: int = 301) -> list[dict]:
        result=[]
        if not ids:
            return result
        for i in range(0,len(ids),35):
            chunk=sorted(ids)[i:i+35]
            for item in chunk:
                _uuid(item)
            query=table+"?select="+cols+"&"+fk+"=in.("+",".join(chunk)+")"
            if extra:
                query+="&"+extra
            rows=self._get(query,limit=limit)
            if any(str(row.get(fk)) not in chunk for row in rows):
                raise RuntimeError("cross-lineage row in read-only inventory")
            result.extend(rows)
            if len(result)>500:
                raise RuntimeError("lineage exceeds verified evidence bound")
        if len({str(item.get("id",i)) for i,item in enumerate(result)}) != len(result):
            raise RuntimeError("duplicate evidence row across pages")
        return result

    def read(self, *, project_key: str, since: datetime,
             run_id: str | None = None):
        if not isinstance(project_key,str) or not PROJECT_KEY.fullmatch(project_key):
            raise ValueError("invalid project key")
        since=_timestamp(since.isoformat()) if isinstance(since,datetime) else _timestamp(since)
        if since>datetime.now(timezone.utc):
            raise ValueError("audit cutoff is in the future")
        if run_id is not None:
            _uuid(run_id)
        project=self._one(
            "factory_projects",
            "select=id,project_key,project_kind,repository,manifest,is_active"
            "&project_key=eq."+quote(project_key,safe=""),
        )
        if project is None or not project.get("is_active"):
            raise RuntimeError("target project is missing or inactive")
        pid=_uuid(project.get("id"))
        if not isinstance(project.get("repository"),str) or "/" not in project["repository"]:
            raise RuntimeError("project has no trustworthy source repository")
        # Only an explicit operator Start admits the journey. Do not treat
        # reconciliations, old runs or a running project as new Start evidence.
        commands=self._get(
            "factory_project_execution_commands?select=project_id,command,actor_id,result,created_at"
            "&project_id=eq."+pid+"&command=eq.start"
            "&created_at=gte."+_utc_filter(since)
            +"&order=created_at.desc",
            limit=51,
        )
        matching=[
            row for row in commands
            if row.get("project_id")==pid
            and isinstance(row.get("result"),dict)
            and isinstance(row["result"].get("run_id"),str)
            and (run_id is None or row["result"]["run_id"]==run_id)
        ]
        # The Console's explicit "submit continuation" action creates an
        # authenticated human audit + deterministic queue receipt in the
        # same transaction, NOT a project_execution_commands/start row.
        # Accept only the exact paired receipts, never a generic queued run.
        if matching:
            start=matching[0]
            root_run_id=_uuid(start["result"]["run_id"])
        else:
            continuation=self._get(
                "factory_audit_events?select=project_id,task_id,run_id,event_type,"
                "actor_type,actor_ref,payload,created_at"
                "&project_id=eq."+pid
                + "&event_type=in.(project.continuation.requested,project.reconciliation.enqueued)"
                + "&created_at=gte."+_utc_filter(since)
                + "&order=created_at.desc",
                limit=101,
            )
            if any(row.get("project_id")!=pid for row in continuation):
                raise RuntimeError("cross-project continuation audit")
            requests=[
                row for row in continuation
                if row.get("event_type")=="project.continuation.requested"
                and row.get("actor_type")=="human"
                and row.get("actor_ref")=="factory-console"
                and isinstance(row.get("payload"),dict)
                and (run_id is None or row.get("run_id")==run_id)
            ]
            eligible=[]
            for request in requests:
                request_id=request["payload"].get("request_id")
                target=request.get("run_id")
                task_id=request.get("task_id")
                if (not isinstance(request_id,str)
                    or not isinstance(target,str)
                    or not isinstance(task_id,str)):
                    continue
                try:
                    _uuid(request_id)
                    _uuid(target)
                    _uuid(task_id)
                except ValueError:
                    continue
                if any(
                    row.get("event_type")=="project.reconciliation.enqueued"
                    and row.get("actor_type")=="system"
                    and row.get("actor_ref")=="factory-console"
                    and row.get("run_id")==target
                    and row.get("task_id")==task_id
                    and isinstance(row.get("payload"),dict)
                    and row["payload"].get("request_id")==request_id
                    and row["payload"].get("task_id")==task_id
                    for row in continuation
                ):
                    eligible.append((request,request_id))
            if not eligible:
                if not commands and not requests and run_id is None:
                    return no_start_report(project_key)
                raise RuntimeError("no verified explicit Start or Console continuation for requested run")
            if len({row["run_id"] for row,_ in eligible})!=len(eligible):
                raise RuntimeError("duplicate operator continuation receipt")
            picked,req_id=eligible[0]
            root_run_id=_uuid(picked["run_id"])
            start={
                "command":"console_continuation",
                "actor_id":"factory-console",
                "result":{"run_id":root_run_id},
                "request_id":req_id,
            }
        root_run=self._one(
            "factory_runs",
            "select=id,task_id,status,candidate_commit,created_at,metadata"
            "&id=eq."+root_run_id,
        )
        if root_run is None:
            raise RuntimeError("Start receipt has no bootstrap run")
        root_task_id=_uuid(root_run.get("task_id"))
        root_task=self._one(
            "factory_tasks",
            "select=id,project_id,parent_task_id,status,created_at"
            "&id=eq."+root_task_id,
        )
        if root_task is None or root_task.get("project_id")!=pid:
            raise RuntimeError("Start points outside project task ownership")
        if start.get("command")=="console_continuation":
            metadata=root_run.get("metadata")
            if (root_task.get("parent_task_id") is not None
                or root_task.get("id")!=next(
                    (row.get("task_id") for row in continuation
                     if row.get("run_id")==root_run_id
                     and row.get("event_type")=="project.continuation.requested"),None)
                or not isinstance(metadata,dict)
                or metadata.get("source")!="factory-console"
                or metadata.get("continuation_request_id")!=start["request_id"]):
                raise RuntimeError("Console continuation is not bound to root run/task")
        start_time=_timestamp(root_task.get("created_at"))
        tasks=self._get(
            "factory_tasks?select=id,project_id,parent_task_id,status,created_at"
            "&project_id=eq."+pid+"&created_at=gte."+_utc_filter(start_time)
            +"&order=created_at.asc,id.asc",
            limit=MAX_PROJECT_TASKS+1,
        )
        if any(row.get("project_id")!=pid for row in tasks):
            raise RuntimeError("task inventory leaked another project")
        children={root_task_id}
        # Resolve only descendants of the Start, independent of stale tasks.
        for _ in range(MAX_PROJECT_TASKS):
            additions={row.get("id") for row in tasks if row.get("parent_task_id") in children}
            new=additions-children
            if not new:
                break
            children.update(new)
        if root_task_id not in {row.get("id") for row in tasks}:
            raise RuntimeError("start bootstrap absent from task lineage")
        runs=self._many_ids(
            "factory_runs",cols="id,task_id,status,candidate_commit,source_commit,branch_name,created_at,metadata",
            fk="task_id",ids=children,
        )
        if root_run_id not in {row.get("id") for row in runs}:
            raise RuntimeError("Start run not present in run lineage")
        run_ids={_uuid(row["id"]) for row in runs}
        sets_all=self._get(
            "factory_change_sets?select=id,project_id,root_task_id,status,source_commit,candidate_commit,integration_branch,metadata,created_at"
            "&project_id=eq."+pid+"&created_at=gte."+_utc_filter(start_time)
            +"&order=created_at.asc,id.asc",
            limit=101,
        )
        if any(cs.get("project_id")!=pid for cs in sets_all):
            raise RuntimeError("cross-project Change Set")
        sets=[cs for cs in sets_all if cs.get("root_task_id") in children]
        cs_ids={_uuid(row["id"]) for row in sets}
        units=self._many_ids(
            "factory_change_set_work_units",
            cols="id,change_set_id,task_id,run_id,status,output_commit,changed_files,created_at",
            fk="change_set_id",ids=cs_ids,
        )
        if any(row.get("task_id") not in children for row in units):
            raise RuntimeError("Change Set work unit is outside Start lineage")
        events=self._get(
            "factory_audit_events?select=id,project_id,task_id,run_id,event_type,actor_type,actor_ref,payload,created_at"
            "&project_id=eq."+pid+"&created_at=gte."+_utc_filter(start_time)
            +"&order=created_at.asc,id.asc",
            limit=MAX_PROJECT_EVENTS+1,
        )
        if any(row.get("project_id")!=pid for row in events):
            raise RuntimeError("cross-project audit evidence")
        # Project-bound SELECT omits historical release receipts written with
        # project_id=NULL. Read only the FOUR known event types for scoped run
        # IDs, and fail closed if a database row violates that contract.
        global_events=self._many_ids(
            "factory_audit_events",
            cols="id,project_id,task_id,run_id,event_type,actor_type,actor_ref,payload,created_at",
            fk="run_id",ids=run_ids,
            extra=("project_id=is.null&event_type=in.("
                   + ",".join(GLOBAL_RELEASE_EVENTS) + ")"),
            limit=201,
        )
        if any(
            row.get("project_id") is not None
            or row.get("event_type") not in GLOBAL_RELEASE_EVENTS
            or row.get("run_id") not in run_ids
            for row in global_events
        ):
            raise RuntimeError("untrusted globally scoped release event")
        events.extend(global_events)
        if len(events)>MAX_PROJECT_EVENTS or len({row.get("id") for row in events})!=len(events):
            raise RuntimeError("release audit inventory exceeded verified bound")
        create_pr=self._many_ids(
            "factory_tool_usage",cols="id,run_id,operation,metadata",fk="run_id",
            ids=run_ids,extra="operation=eq.create_pr",
        )
        reconcile_pr=self._many_ids(
            "factory_tool_usage",cols="id,run_id,operation,metadata",fk="run_id",
            ids=run_ids,extra="operation=eq.reconcile_pr_candidate",
        )
        deploy=self._many_ids(
            "factory_deployments",cols="id,run_id,environment,status,metadata",fk="run_id",
            ids=run_ids,
        )
        release_reports=self._get(
            "factory_release_reports?select=id,project_id,run_id,candidate_commit,status,created_at"
            "&project_id=eq."+pid+"&created_at=gte."+_utc_filter(start_time),
            limit=101,
        )
        release_reports=[row for row in release_reports if row.get("run_id") in run_ids]
        # A create_pr receipt is immutable. The only legitimate new SHA
        # after a repair is an exact, atomically audited reconciliation whose
        # original candidate is an ancestor of the repaired candidate.
        shas={cs.get("candidate_commit") for cs in sets if
              isinstance(cs.get("candidate_commit"),str) and SHA.fullmatch(cs["candidate_commit"])}
        matches=[]
        for cs in sets:
            target=cs.get("candidate_commit")
            if target not in shas:
                continue
            for entry in create_pr:
                meta=entry.get("metadata")
                if not isinstance(meta,dict) or meta.get("change_set_id")!=cs.get("id"):
                    continue
                original=meta.get("head_sha")
                number=meta.get("pr")
                if not isinstance(original,str) or not SHA.fullmatch(original) or type(number) is not int or number<1:
                    continue
                if target==original:
                    matches.append((cs,entry,None))
                else:
                    for rec in reconcile_pr:
                        data=rec.get("metadata")
                        if (rec.get("run_id")==entry.get("run_id")
                            and isinstance(data,dict)
                            and data.get("previous_commit")==original
                            and data.get("candidate_commit")==target
                            and data.get("change_set_id")==cs.get("id")
                            and str(data.get("pr_number"))==str(number)):
                            matches.append((cs,entry,rec))
        github_evidence=None
        preview_required=None
        if len(matches)>1:
            raise RuntimeError("multiple candidate identities fit the same Start lineage")
        if len(matches)==1:
            cs,create,repair=matches[0]
            meta=create["metadata"]
            pr_number=meta["pr"]
            original=meta["head_sha"]
            target=cs["candidate_commit"]
            github=self.github_factory(repository=project["repository"])
            pr=github.get_pull_request(pr_number)
            release_request=(cs.get("metadata") or {}).get("integration_release_request") or {}
            exact_branch=cs.get("integration_branch")
            reconciliation_verified=repair is None
            if repair is not None:
                reconciliation_verified=bool(
                    isinstance(exact_branch,str)
                    and validate_reconciliation_receipt(
                        github,receipt=repair["metadata"],old_sha=original,
                        candidate_sha=target,pr_number=pr_number,
                        repository=project["repository"],change_set_id=cs["id"],
                        branch=exact_branch,
                    )
                )
            # Never promote an unverified updated PR head as a valid source
            # of CI, release or model-generated implementation evidence.
            if reconciliation_verified and pr.head_sha==target and (
                pr.head_repository==project["repository"]
                and (repair is None or
                     release_request.get("candidate_commit")==target)
            ):
                paths=github.get_pull_request_files(pr_number)
                policy=evaluate_preview_applicability(
                    manifest=project.get("manifest") or {},
                    changed_files=paths,
                )
                preview_required=policy.required
                selected_units=[
                    row for row in units
                    if row.get("change_set_id")==cs["id"]
                    and row.get("run_id") in run_ids
                ]
                if len(selected_units)>30:
                    raise RuntimeError("commit verification exceeds bounded limit")
                completed=[
                    row["output_commit"] for row in selected_units
                    if row.get("status") in ("completed","integrated")
                    and isinstance(row.get("output_commit"),str)
                    and SHA.fullmatch(row["output_commit"])
                ]
                if len(completed)!=len(selected_units) or not completed:
                    commits_ok=False
                elif all(isinstance(row.get("changed_files"),list)
                         and row.get("changed_files") for row in selected_units):
                    commits_ok=verify_copied_work_units(
                        github,original_candidate=original,
                        final_candidate=target,units=selected_units,
                    )
                else:
                    # Legacy direct-commit path: requires real ancestry, not
                    # merely a commit object existing in the repository.
                    commits_ok=candidate_contains_work_units(
                        github,target,set(completed)
                    )
                github_evidence={
                    "repository":project["repository"],"number":pr.number,
                    "head_sha":pr.head_sha,"head_repository":pr.head_repository,
                    "base_ref":pr.base_ref,"merged":pr.merged,
                    "merge_commit_sha":pr.merge_commit_sha,
                    "work_unit_commit_verified":commits_ok,
                    "candidate_reconciliation_verified":reconciliation_verified,
                    "ci_state":github.get_ci_state(pr_number),
                }
        return evaluate_journey(
            project=project,root_run_id=root_run_id,start_command=start,
            runs=runs,events=events,change_sets=sets,work_units=units,
            create_pr_receipts=create_pr,deployments=deploy,
            release_reports=release_reports,github=github_evidence,
            preview_required=preview_required,
            candidate_reconciliations=reconcile_pr,
        )
