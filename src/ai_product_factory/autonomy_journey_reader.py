"""Strict read-only adapters for fresh, operator-started autonomy journeys."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

from .autonomy_journey import evaluate_journey, no_start_report, SHA
from .journey_candidate_provenance import (
    validate_reconciliation_receipt, verify_copied_work_units,
    verify_copied_work_unit_waves,
)
from .journey_github_witness import observe_candidate, require_unchanged_candidate
from .github_rest import GitHubRestAdapter
from .github_owner_start import (
    FACTORY_REPO as OWNER_START_REPO,
    OWNER_ID as OWNER_START_ID,
    OWNER_LOGIN as OWNER_START_LOGIN,
    ISSUE_NUMBER as OWNER_START_ISSUE,
    request_uuid as github_owner_request_uuid,
)
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




def _valid_github_owner_request(payload: object) -> bool:
    """The owner event must bind immutable issue/comment/actor to request id."""
    if not isinstance(payload, dict) or payload.get("source")!="github-owner":
        return False
    github=payload.get("github")
    if (not isinstance(github,dict)
        or github.get("repository")!=OWNER_START_REPO
        or type(github.get("issue_number")) is not int
        or github["issue_number"]!=OWNER_START_ISSUE
        or type(github.get("actor_id")) is not int
        or github["actor_id"]!=OWNER_START_ID
        or github.get("actor_login")!=OWNER_START_LOGIN
        or type(github.get("comment_id")) is not int
        or github["comment_id"]<=0
        or type(payload.get("attachment_count")) is not int
        or payload["attachment_count"]!=0):
        return False
    return payload.get("request_id")==github_owner_request_uuid(
        OWNER_START_ISSUE, github["comment_id"]
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

    def _verified_nonproduction_integration(
        self, *, github, repository: str, project_id: str, events: list[dict],
        release_run_id: str, candidate_sha: str, pr_number: int,
        head_ref: str, base_ref: str, merge_sha: str,
    ) -> bool:
        """Attest exact preview merge plus the independent post-merge browser.

        The release observer has already written a service-only, atomic audit.
        Re-read its identity, the persisted browser snapshot and the current
        GitHub ref. This is NOT production release authority and writes nothing.
        """
        if (not base_ref.startswith("preview/") or base_ref == "preview/"
            or not isinstance(merge_sha, str) or not SHA.fullmatch(merge_sha)
            or candidate_sha == merge_sha):
            return False
        matches = [
            row for row in events
            if row.get("event_type") == "change_set.nonproduction_merge.observed"
            and row.get("project_id") == project_id
            and row.get("run_id") == release_run_id
        ]
        if len(matches) != 1:
            return False
        row = matches[0]
        p = row.get("payload")
        if (row.get("actor_ref") != "nonproduction-release-observer"
            or not isinstance(p, dict)
            or p.get("repository") != repository
            or str(p.get("pr_number")) != str(pr_number)
            or p.get("candidate_commit") != candidate_sha
            or p.get("head_sha") != candidate_sha
            or p.get("head_ref") != head_ref
            or p.get("base_ref") != base_ref
            or p.get("merge_sha") != merge_sha
            or p.get("observed_base_tip") != merge_sha
            or p.get("production_main_sha") == merge_sha
            or not isinstance(p.get("production_main_sha"), str)
            or not SHA.fullmatch(p["production_main_sha"])
            or p.get("merged") is not True
            or p.get("vercel_state") != "success"
            or p.get("merge_is_ancestor") is not True
            or p.get("production_released") is not False
            or p.get("production_release_completed") is not False
            or p.get("environment") != "preview"):
            return False
        try:
            snapshot_id = _uuid(p.get("postmerge_browser_snapshot_id"))
        except ValueError:
            return False
        snapshot = self._one(
            "factory_project_state_snapshots",
            "select=id,project_id,observed_stage,evidence,gaps,constraints,source_status"
            "&project_id=eq." + project_id + "&id=eq." + snapshot_id,
        )
        if snapshot is None or snapshot.get("id") != snapshot_id:
            return False
        evidence = snapshot.get("evidence")
        preview = evidence.get("preview") if isinstance(evidence, dict) else None
        constraints = snapshot.get("constraints")
        source = snapshot.get("source_status")
        url = p.get("postmerge_preview_url")
        parsed = urlparse(url) if isinstance(url, str) else None
        if (snapshot.get("project_id") != project_id
            or snapshot.get("observed_stage") != "verification"
            or snapshot.get("gaps") != []
            or not isinstance(evidence, dict)
            or evidence.get("candidate_commit") != merge_sha
            or evidence.get("target_repository") != repository
            or not isinstance(preview, dict)
            or preview.get("provider") != "vercel"
            or preview.get("status") != "browser_verified"
            or preview.get("url") != url
            or str(preview.get("browser_verifier_run_id")) != str(p.get("verifier_run_id"))
            or not isinstance(preview.get("browser_verifier_run_id"), int)
            or isinstance(preview.get("browser_verifier_run_id"), bool)
            or preview["browser_verifier_run_id"] <= 0
            or not isinstance(constraints, dict)
            or constraints.get("production_merge_authorized") is not False
            or not isinstance(source, dict)
            or source.get("browser_visual_validation") != "success"
            or source.get("vercel_preview") != "resolved"
            or parsed is None or parsed.scheme != "https"
            or not (parsed.hostname or "").endswith(".vercel.app")
            or parsed.username is not None or parsed.password is not None):
            return False
        base_tip = github.get_branch_sha(base_ref)
        main_tip = github.get_branch_sha("main")
        if (not isinstance(base_tip, str) or not SHA.fullmatch(base_tip)
            or not isinstance(main_tip, str) or not SHA.fullmatch(main_tip)
            or main_tip == merge_sha):
            return False
        if base_tip != merge_sha:
            compare = github.compare_commits(merge_sha, base_tip)
            if (not isinstance(compare, dict) or compare.get("status") != "ahead"
                or compare.get("behind_by") != 0
                or type(compare.get("ahead_by")) is not int
                or not 1 <= compare["ahead_by"] <= 20):
                return False
        # A preview merge already promoted to main must not be reported as a
        # preview-only integration. An unrelated/diverged production main is OK.
        production_compare = github.compare_commits(merge_sha, main_tip)
        if (not isinstance(production_compare, dict)
            or (production_compare.get("status") in ("ahead", "identical")
                and production_compare.get("behind_by") == 0)):
            return False
        return github.get_branch_sha(base_ref) == base_tip


    def _console_greenfield_intake_start(
        self, project: dict, requested_run: str | None, since: datetime,
    ) -> dict | None:
        """Recognize only the atomic, operator-authenticated Console intake.

        Historical bootstrap events alone are not Start authority. The three
        distinct audit receipts must share the project's creation transaction,
        and the manifest must bind a canonical request/operator identity.
        """
        manifest=project.get("manifest")
        if (project.get("project_kind")!="greenfield"
            or not isinstance(manifest,dict)
            or manifest.get("source")!="factory-console"
            or manifest.get("onboarding_mode")!="greenfield"
            or "bootstrap_request_id" not in manifest):
            return None
        if manifest.get("reconcile_first") is True:
            raise RuntimeError("greenfield intake unexpectedly chose reconciliation")
        born=_timestamp(project.get("created_at"))
        if born<since:
            return None
        draft=_uuid(manifest.get("bootstrap_request_id"))
        operator=_uuid(manifest.get("bootstrap_operator_id"))
        count=manifest.get("bootstrap_attachment_count")
        if type(count) is not int or not 0<=count<=10:
            raise RuntimeError("invalid atomic intake attachment count")
        pid=_uuid(project.get("id"))
        rows=self._get(
            "factory_audit_events?select=id,project_id,task_id,run_id,event_type,"
            "actor_type,actor_ref,payload,created_at"
            "&project_id=eq."+pid+
            "&event_type=in.(project.intake.created,project.attachments.finalized,project.bootstrap.enqueued)"
            "&order=created_at.asc,id.asc",limit=15,
        )
        receipts=[row for row in rows if _timestamp(row.get("created_at"))==born]
        if (len(receipts)!=3 or
            [row.get("event_type") for row in receipts]!=[
                "project.intake.created",
                "project.attachments.finalized",
                "project.bootstrap.enqueued",
            ] or any(row.get("project_id")!=pid for row in receipts)
            or any(type(row.get("id")) is not int for row in receipts)
            or not (receipts[0]["id"]<receipts[1]["id"]<receipts[2]["id"])):
            raise RuntimeError("atomic Console intake has no unique ordered audit trio")
        intake,finalized,bootstrap=receipts
        if (any(row.get("actor_ref")!="factory-console" for row in receipts)
            or [row.get("actor_type") for row in receipts]!=["human","human","system"]
            or any(row.get("task_id") is not None for row in receipts)
            or intake.get("run_id") is not None
            or finalized.get("run_id") is not None
            or not isinstance(intake.get("payload"),dict)
            or intake["payload"].get("project_key")!=project.get("project_key")
            or intake["payload"].get("project_kind")!="greenfield"
            or not isinstance(finalized.get("payload"),dict)
            or finalized["payload"].get("draft_id")!=draft
            or type(finalized["payload"].get("count")) is not int
            or finalized["payload"]["count"]!=count
            or not isinstance(bootstrap.get("payload"),dict)):
            raise RuntimeError("atomic Console intake actor/request evidence is incomplete")
        bootstrap_run=_uuid(bootstrap.get("run_id"))
        bootstrap_task=_uuid(bootstrap["payload"].get("task_id"))
        if requested_run is not None and requested_run!=bootstrap_run:
            raise RuntimeError("explicit audit run differs from Console intake")
        return {
            "command":"console_greenfield_intake","actor_id":operator,
            "request_id":draft,"attachment_count":count,
            "bootstrap_task_id":bootstrap_task,
            "result":{"run_id":bootstrap_run},
        }

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
            "select=id,project_key,project_kind,repository,manifest,is_active,created_at"
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
                and row.get("actor_ref") in ("factory-console","github-owner")
                and isinstance(row.get("payload"),dict)
                and (run_id is None or row.get("run_id")==run_id)
            ]
            eligible=[]
            for request in requests:
                request_id=request["payload"].get("request_id")
                target=request.get("run_id")
                task_id=request.get("task_id")
                actor_ref=request.get("actor_ref")
                if actor_ref=="github-owner" and not _valid_github_owner_request(request["payload"]):
                    continue
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
                    and row.get("actor_ref")==actor_ref
                    and row.get("run_id")==target
                    and row.get("task_id")==task_id
                    and isinstance(row.get("payload"),dict)
                    and row["payload"].get("request_id")==request_id
                    and row["payload"].get("task_id")==task_id
                    and (actor_ref=="factory-console" or (
                        row["payload"].get("source")=="github-owner"
                        and row["payload"].get("github")==request["payload"].get("github")
                    ))
                    for row in continuation
                ):
                    eligible.append((request,request_id))
            if eligible:
                if len({row["run_id"] for row,_ in eligible})!=len(eligible):
                    raise RuntimeError("duplicate operator continuation receipt")
                picked,req_id=eligible[0]
                root_run_id=_uuid(picked["run_id"])
                github_origin=picked["payload"].get("github") if picked.get("actor_ref")=="github-owner" else None
                start={
                    "command":"github_owner_continuation" if github_origin else "console_continuation",
                    "actor_id":str(OWNER_START_ID) if github_origin else "factory-console",
                    "result":{"run_id":root_run_id},
                    "request_id":req_id,
                    "github_origin":github_origin,
                }
            else:
                start=self._console_greenfield_intake_start(project,run_id,since)
                if start is None:
                    if not commands and not requests and run_id is None:
                        return no_start_report(project_key)
                    raise RuntimeError("no verified explicit Start or Console continuation for requested run")
                root_run_id=_uuid(start["result"]["run_id"])
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
            "select=id,project_id,parent_task_id,status,created_at,external_key"
            "&id=eq."+root_task_id,
        )
        if root_task is None or root_task.get("project_id")!=pid:
            raise RuntimeError("Start points outside project task ownership")
        if start.get("command") in {"console_continuation","github_owner_continuation"}:
            metadata=root_run.get("metadata")
            actor_source="github-owner" if start["command"]=="github_owner_continuation" else "factory-console"
            if (root_task.get("parent_task_id") is not None
                or root_task.get("id")!=next(
                    (row.get("task_id") for row in continuation
                     if row.get("run_id")==root_run_id
                     and row.get("event_type")=="project.continuation.requested"),None)
                or not isinstance(metadata,dict)
                or metadata.get("source")!=actor_source
                or metadata.get("continuation_request_id")!=start["request_id"]
                or (start["command"]=="github_owner_continuation" and (
                    not isinstance(metadata.get("continuation_request"),dict)
                    or metadata["continuation_request"].get("github")!=start["github_origin"]
                    or metadata["continuation_request"].get("attachment_count")!=0
                ))):
                raise RuntimeError("Owner continuation is not bound to root run/task")
        if start.get("command")=="console_greenfield_intake":
            metadata=root_run.get("metadata")
            born=_timestamp(project.get("created_at"))
            if (root_task.get("parent_task_id") is not None
                or root_task.get("external_key")!="product-bootstrap-v1"
                or root_task_id!=start["bootstrap_task_id"]
                or _timestamp(root_task.get("created_at"))!=born
                or _timestamp(root_run.get("created_at"))!=born
                or not isinstance(metadata,dict)
                or metadata.get("source")!="factory-console"
                or metadata.get("stages")!=["discovery","specification","planning"]):
                raise RuntimeError("Console greenfield Start lacks exact root task/run identity")
            manifest=project["manifest"]
            attachments=self._get(
                "factory_project_attachments?select=project_id,draft_id,operator_user_id,finalized_at"
                "&project_id=eq."+pid+"&order=created_at.asc",limit=12,
            )
            if (len(attachments)!=start["attachment_count"]
                or any(row.get("project_id")!=pid
                       or row.get("draft_id")!=start["request_id"]
                       or row.get("operator_user_id")!=start["actor_id"]
                       or not isinstance(row.get("finalized_at"),str)
                       for row in attachments)):
                raise RuntimeError("atomic Console intake attachment ownership mismatch")
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
            "factory_tool_usage",cols="id,run_id,operation,metadata,created_at",fk="run_id",
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
            # Never combine files or green CI observed after a candidate PR
            # moved with an earlier PR snapshot. Validate exact PR/ref before
            # the reads and once more AFTER get_ci_state (which re-reads PR).
            if reconciliation_verified and (
                repair is None or release_request.get("candidate_commit")==target
            ):
                witness=observe_candidate(
                    github,number=pr_number,sha=target,
                    repository=project["repository"],branch=exact_branch,
                )
                paths=github.get_pull_request_files(pr_number)
                if (not isinstance(paths,(tuple,list)) or not paths
                    or any(not isinstance(p,str) or not p for p in paths)):
                    raise RuntimeError("candidate changed-file evidence is unavailable")
                policy=evaluate_preview_applicability(
                    manifest=project.get("manifest") or {},
                    changed_files=tuple(paths),
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
                    # A CI repair creates another exact PR candidate. Verify
                    # each Work Unit's source bytes at the FIRST subsequent
                    # candidate, not against files a later repair legitimately
                    # replaced. Every wave still requires immutable provenance.
                    wave_receipts=[
                        entry for entry in create_pr
                        if isinstance(entry.get("metadata"),dict)
                        and entry["metadata"].get("change_set_id")==cs["id"]
                        and entry["metadata"].get("pr")==pr_number
                    ]
                    if len(wave_receipts)>1:
                        commits_ok=verify_copied_work_unit_waves(
                            github,final_candidate=target,units=selected_units,
                            receipts=wave_receipts,change_set_id=cs["id"],
                            pr_number=pr_number,
                        )
                    else:
                        commits_ok=verify_copied_work_units(
                            github,original_candidate=original,
                            final_candidate=target,units=selected_units,
                        )
                else:
                    # Legacy direct-commit path: require exact ancestry, not
                    # merely an existing object in the GitHub repository.
                    commits_ok=candidate_contains_work_units(
                        github,target,set(completed)
                    )
                ci_state=github.get_ci_state(pr_number)
                require_unchanged_candidate(github,witness)
                github_evidence={
                    "repository":project["repository"],"number":witness.number,
                    "head_sha":witness.head_sha,
                    "head_repository":witness.head_repository,
                    "base_ref":witness.base_ref,"merged":witness.merged,
                    "merge_commit_sha":witness.merge_sha,
                    "work_unit_commit_verified":commits_ok,
                    "candidate_reconciliation_verified":reconciliation_verified,
                    "ci_state":ci_state,
                }
                if witness.merged and witness.base_ref.startswith("preview/"):
                    github_evidence["nonproduction_integration_verified"] = (
                        self._verified_nonproduction_integration(
                            github=github,repository=project["repository"],
                            project_id=pid,events=events,
                            release_run_id=create["run_id"],candidate_sha=target,
                            pr_number=pr_number,head_ref=witness.head_ref,
                            base_ref=witness.base_ref,merge_sha=witness.merge_sha,
                        )
                    )
                    # Snapshot and branch reads may race another PR update.
                    require_unchanged_candidate(github,witness)
        return evaluate_journey(
            project=project,root_run_id=root_run_id,start_command=start,
            runs=runs,events=events,change_sets=sets,work_units=units,
            create_pr_receipts=create_pr,deployments=deploy,
            release_reports=release_reports,github=github_evidence,
            preview_required=preview_required,
            candidate_reconciliations=reconcile_pr,
        )
