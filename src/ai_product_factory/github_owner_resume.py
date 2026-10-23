"""Owner-only, no-model, checkpointed planning recovery entrypoint.

The public GitHub issue command only admits a specifically failed root run.
Durable PostgreSQL evidence verifies every predecessor stage, so this route
cannot forge a completed Product Stage or replay paid discovery.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable, Mapping
from urllib import error
from uuid import UUID

from .github_owner_start import (
    FACTORY_REPO, REPO_ID, OWNER_ID, OWNER_LOGIN, ISSUE_NUMBER,
    _default_post, _WORKFLOW_DISPATCH, MAX_EVENT_BYTES,
)
from .supabase_server import resolve_supabase_server_config

COMMAND = re.compile(
    r"/factory-resume-planning run=([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}"
    r"-[89ab][0-9a-f]{3}-[0-9a-f]{12})\Z", re.ASCII
)
RPC = "/rest/v1/rpc/factory_resume_failed_product_planning_v1"
POST = Callable[[str,dict,dict[str,str]],tuple[int,object]]


class OwnerResumeBlocked(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def parse_owner_resume_event(event: object, environ: Mapping[str,str]) -> dict:
    if (not isinstance(event,dict)
        or environ.get("GITHUB_EVENT_NAME")!="issue_comment"
        or environ.get("GITHUB_REPOSITORY")!=FACTORY_REPO
        or environ.get("GITHUB_REF")!="refs/heads/main"
        or environ.get("GITHUB_ACTOR")!=OWNER_LOGIN
        or event.get("action")!="created"):
        raise OwnerResumeBlocked("invalid_event_identity")
    repo,issue,comment,sender=(event.get(v) for v in (
        "repository","issue","comment","sender"
    ))
    if (not all(isinstance(x,dict) for x in (repo,issue,comment,sender))
        or repo.get("full_name")!=FACTORY_REPO
        or type(repo.get("id")) is not int or repo["id"]!=REPO_ID
        or not isinstance(repo.get("owner"),dict)
        or type(repo["owner"].get("id")) is not int
        or repo["owner"]["id"]!=OWNER_ID
        or issue.get("number")!=ISSUE_NUMBER
        or type(issue.get("number")) is not int
        or issue.get("state")!="open"
        or issue.get("pull_request") is not None
        or type(comment.get("id")) is not int or comment["id"]<=0
        or comment.get("author_association")!="OWNER"
        or not isinstance(comment.get("user"),dict)
        or comment["user"].get("login")!=OWNER_LOGIN
        or type(comment["user"].get("id")) is not int
        or comment["user"]["id"]!=OWNER_ID
        or sender.get("login")!=OWNER_LOGIN
        or type(sender.get("id")) is not int or sender["id"]!=OWNER_ID):
        raise OwnerResumeBlocked("invalid_event_identity")
    body=comment.get("body")
    if not isinstance(body,str) or len(body)>128:
        raise OwnerResumeBlocked("invalid_command")
    match=COMMAND.fullmatch(body)
    if match is None:
        raise OwnerResumeBlocked("invalid_command")
    source_id=match.group(1)
    if str(UUID(source_id))!=source_id:
        raise OwnerResumeBlocked("invalid_command")
    return {
        "source_run_id":source_id,
        "comment_id":comment["id"],
        "issue_number":ISSUE_NUMBER,
        "actor_id":OWNER_ID,
        "actor_login":OWNER_LOGIN,
    }


def read_event(path: str, env: Mapping[str,str]) -> dict:
    file=Path(path)
    if not file.is_file() or file.stat().st_size>MAX_EVENT_BYTES:
        raise OwnerResumeBlocked("invalid_event_identity")
    try:
        data=json.loads(file.read_text(encoding="utf-8"))
    except (UnicodeDecodeError,ValueError):
        raise OwnerResumeBlocked("invalid_event_identity") from None
    return parse_owner_resume_event(data,env)


def queue_checkpointed_planning(
    cmd: dict, env: Mapping[str,str], *, post: POST = _default_post,
) -> dict:
    try:
        cfg=resolve_supabase_server_config(
            url=env.get("SUPABASE_URL",""),
            secret_key=env.get("SUPABASE_SECRET_KEY",""),
            service_role_key=env.get("SUPABASE_SERVICE_ROLE_KEY",""),
        )
    except (ValueError,RuntimeError):
        raise OwnerResumeBlocked("control_plane_unavailable") from None
    try:
        status,payload=post(
            cfg.url+RPC,{
                "p_source_run_id":cmd["source_run_id"],
                "p_comment_id":cmd["comment_id"],
                "p_issue_number":cmd["issue_number"],
                "p_actor_id":cmd["actor_id"],
                "p_actor_login":cmd["actor_login"],
            },{**cfg.headers,"Content-Type":"application/json"}
        )
    except error.HTTPError as exc:
        if exc.code==404:
            raise OwnerResumeBlocked("resume_migration_not_applied") from None
        if exc.code in (400,403,409):
            raise OwnerResumeBlocked("checkpoint_provenance_blocked") from None
        raise OwnerResumeBlocked("control_plane_unavailable") from None
    except (OSError,TimeoutError):
        raise OwnerResumeBlocked("control_plane_unavailable") from None
    if status not in (200,201) or not isinstance(payload,dict):
        raise OwnerResumeBlocked("invalid_control_plane_receipt")
    try:
        rid=str(UUID(payload["run_id"]))
        task=str(UUID(payload["task_id"]))
        project=str(UUID(payload["project_id"]))
    except (ValueError,KeyError,TypeError,AttributeError):
        raise OwnerResumeBlocked("invalid_control_plane_receipt") from None
    key=payload.get("project_key")
    if (payload.get("source_run_id")!=cmd["source_run_id"]
        or payload.get("source")!="checkpointed_product_planning_v1"
        or payload.get("stages")!=["planning"]
        or type(payload.get("created")) is not bool
        or not isinstance(key,str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_-]{0,99}",key,re.ASCII
        )
        or len({rid,task,project,cmd["source_run_id"]})!=4
        or (payload["created"] and (
            type(payload.get("generation")) is not int or payload["generation"]<1))):
        raise OwnerResumeBlocked("invalid_control_plane_receipt")
    result={
        "status":"enqueued" if payload["created"] else "replayed",
        "source_run_id":cmd["source_run_id"],
        "run_id":rid,"project_key":key,
        "created":payload["created"],"stages":["planning"],
        "paid_calls":0,"release_authorized":False,"wake":"not_needed",
    }
    if not payload["created"]:
        return result
    token=env.get("GITHUB_TOKEN","").strip()
    if not token:
        result.update(status="enqueued_wake_unavailable",wake="failed")
        return result
    try:
        wake_status,_=post(
            _WORKFLOW_DISPATCH,
            {"ref":"main","inputs":{"project_key":key}},
            {"Authorization":"Bearer "+token,
             "Accept":"application/vnd.github+json",
             "Content-Type":"application/json",
             "X-GitHub-Api-Version":"2022-11-28"},
        )
        result["wake"]="requested" if wake_status==204 else "failed"
    except (error.HTTPError,OSError,TimeoutError):
        result["wake"]="failed"
    if result["wake"]!="requested":
        result["status"]="enqueued_wake_unavailable"
    return result


def main(argv: list[str]|None=None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--event-path",required=True)
    parser.add_argument("--mode",choices=("validate","enqueue"),required=True)
    parser.add_argument("--output")
    args=parser.parse_args(argv)
    result={"status":"blocked","reason":"invalid_event_identity",
            "paid_calls":0,"release_authorized":False}
    code=2
    try:
        command=read_event(args.event_path,os.environ)
        if args.mode=="validate":
            print("Owner planning resume identity verified")
            return 0
        result=queue_checkpointed_planning(command,os.environ)
        code=0 if result["status"] in ("enqueued","replayed") else 3
    except OwnerResumeBlocked as exc:
        result["reason"]=exc.code
    except (OSError,ValueError,RuntimeError):
        result["reason"]="unverifiable"
    if args.output and args.mode=="enqueue":
        Path(args.output).write_text(json.dumps(result,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
    return code


if __name__=="__main__":
    sys.exit(main())
