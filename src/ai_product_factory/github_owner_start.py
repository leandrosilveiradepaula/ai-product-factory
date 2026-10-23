"""Exact OWNER issue-comment Start, isolated from Console and paid model lanes.

Only an event signed by GitHub Actions and accepted by the OIDC broker may
reach the service-only PostgreSQL RPC. A caller cannot claim to be a Console
operator. The GitHub wake happens only after durable transaction commit.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable, Mapping
from urllib import error, request
from uuid import UUID

from .supabase_server import resolve_supabase_server_config

FACTORY_REPO = "leandrosilveiradepaula/ai-product-factory"
REPO_ID = 1387883686
OWNER_ID = 256917842
OWNER_LOGIN = "leandrosilveiradepaula"
ISSUE_NUMBER = 1055
COMMAND = re.compile(r"/factory-start ([a-z0-9][a-z0-9_-]{0,99})\Z", re.ASCII)
MAX_REQUEST_CHARS = 6000
MAX_EVENT_BYTES = 131072
_RPC = "/rest/v1/rpc/factory_enqueue_github_owner_continuation_v1"
_WORKFLOW_DISPATCH = (
    "https://api.github.com/repos/" + FACTORY_REPO
    + "/actions/workflows/autonomous-runner.yml/dispatches"
)
Post = Callable[[str, dict, dict[str, str]], tuple[int, object]]


class OwnerStartBlocked(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OwnerStartCommand:
    project_key: str
    request: str
    comment_id: int
    issue_number: int
    actor_id: int
    actor_login: str
    request_id: str


def request_uuid(issue_number: int, comment_id: int) -> str:
    if issue_number != ISSUE_NUMBER or type(comment_id) is not int or comment_id <= 0:
        raise OwnerStartBlocked("invalid_event_identity")
    # MD5 is strictly an idempotent name-to-UUID mapping, NOT an auth primitive.
    payload = f"factory-owner-start-v1:{issue_number}:{comment_id}".encode("ascii")
    return str(UUID(hex=hashlib.md5(payload).hexdigest()))


def parse_owner_start_event(event: object, environ: Mapping[str, str]) -> OwnerStartCommand:
    """Validate all independent GitHub identities before privileged OIDC."""
    if (not isinstance(event, dict)
        or environ.get("GITHUB_EVENT_NAME") != "issue_comment"
        or environ.get("GITHUB_REPOSITORY") != FACTORY_REPO
        or environ.get("GITHUB_REF") != "refs/heads/main"
        or environ.get("GITHUB_ACTOR") != OWNER_LOGIN
        or event.get("action") != "created"):
        raise OwnerStartBlocked("invalid_event_identity")

    repo = event.get("repository")
    issue = event.get("issue")
    comment = event.get("comment")
    sender = event.get("sender")
    if (not isinstance(repo, dict)
        or repo.get("full_name") != FACTORY_REPO
        or type(repo.get("id")) is not int or repo["id"] != REPO_ID
        or not isinstance(repo.get("owner"), dict)
        or type(repo["owner"].get("id")) is not int
        or repo["owner"]["id"] != OWNER_ID
        or not isinstance(issue, dict)
        or type(issue.get("number")) is not int or issue["number"] != ISSUE_NUMBER
        or issue.get("state") != "open"
        or issue.get("pull_request") is not None
        or not isinstance(comment, dict)
        or comment.get("author_association") != "OWNER"
        or type(comment.get("id")) is not int or comment["id"] <= 0
        or not isinstance(comment.get("user"), dict)
        or comment["user"].get("login") != OWNER_LOGIN
        or type(comment["user"].get("id")) is not int
        or comment["user"]["id"] != OWNER_ID
        or not isinstance(sender, dict)
        or sender.get("login") != OWNER_LOGIN
        or type(sender.get("id")) is not int or sender["id"] != OWNER_ID):
        raise OwnerStartBlocked("invalid_event_identity")

    body = comment.get("body")
    if not isinstance(body, str) or len(body.encode("utf-8")) > 25000:
        raise OwnerStartBlocked("invalid_command")
    normalized = body.replace("\r\n", "\n")
    if any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127
           for c in normalized):
        raise OwnerStartBlocked("invalid_command")
    header, separator, raw_request = normalized.partition("\n")
    match = COMMAND.fullmatch(header)
    if not separator or not match:
        raise OwnerStartBlocked("invalid_command")
    description = raw_request.strip()
    if not 1 <= len(description) <= MAX_REQUEST_CHARS:
        raise OwnerStartBlocked("invalid_command")
    return OwnerStartCommand(
        project_key=match.group(1),
        request=description,
        comment_id=comment["id"],
        issue_number=ISSUE_NUMBER,
        actor_id=OWNER_ID,
        actor_login=OWNER_LOGIN,
        request_id=request_uuid(ISSUE_NUMBER, comment["id"]),
    )


def read_event(path: str, environ: Mapping[str, str]) -> OwnerStartCommand:
    source = Path(path)
    if not source.is_file() or source.stat().st_size > MAX_EVENT_BYTES:
        raise OwnerStartBlocked("invalid_event_identity")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise OwnerStartBlocked("invalid_event_identity") from None
    return parse_owner_start_event(data, environ)


def _default_post(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, object]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=30) as reply:
        response = reply.read()
        if len(response) > 16384:
            raise OwnerStartBlocked("invalid_control_plane_receipt")
        if not response:
            return reply.status, None
        return reply.status, json.loads(response.decode("utf-8"))


def enqueue_owner_start(
    command: OwnerStartCommand, environ: Mapping[str, str],
    *, post: Post = _default_post,
) -> dict:
    """Only one authorized service-role RPC, then best-effort local workflow wake."""
    try:
        cfg = resolve_supabase_server_config(
            url=environ.get("SUPABASE_URL", ""),
            secret_key=environ.get("SUPABASE_SECRET_KEY", ""),
            service_role_key=environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        )
    except (ValueError, RuntimeError):
        raise OwnerStartBlocked("control_plane_unavailable") from None
    try:
        status, payload = post(
            cfg.url + _RPC,
            {
                "p_project_key": command.project_key,
                "p_request": command.request,
                "p_comment_id": command.comment_id,
                "p_issue_number": command.issue_number,
                "p_actor_id": command.actor_id,
                "p_actor_login": command.actor_login,
            },
            {**cfg.headers, "Content-Type": "application/json"},
        )
    except error.HTTPError as exc:
        if exc.code == 404:
            raise OwnerStartBlocked("owner_start_migration_not_applied") from None
        if exc.code in (400, 403, 409):
            raise OwnerStartBlocked("control_plane_admission_blocked") from None
        raise OwnerStartBlocked("control_plane_unavailable") from None
    except (OSError, TimeoutError):
        raise OwnerStartBlocked("control_plane_unavailable") from None
    if status not in (200, 201) or not isinstance(payload, dict):
        raise OwnerStartBlocked("invalid_control_plane_receipt")
    try:
        project_id = str(UUID(str(payload["project_id"])))
        task_id = str(UUID(str(payload["task_id"])))
        run_id = str(UUID(str(payload["run_id"])))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise OwnerStartBlocked("invalid_control_plane_receipt") from None
    if (payload.get("request_id") != command.request_id
        or payload.get("source") != "github-owner"
        or type(payload.get("created")) is not bool
        or project_id == task_id or task_id == run_id
        or (payload["created"] and (
            type(payload.get("generation")) is not int or payload["generation"] < 1))):
        raise OwnerStartBlocked("invalid_control_plane_receipt")

    receipt = {
        "status": "enqueued" if payload["created"] else "replayed",
        "project_key": command.project_key,
        "request_id": command.request_id,
        "task_id": task_id,
        "run_id": run_id,
        "created": payload["created"],
        "wake": "not_needed",
        "source": "github-owner",
        "ready_for_production": False,
        "paid_calls": 0,
    }
    if not payload["created"]:
        return receipt
    # Dispatch is only a hint AFTER durable COMMIT. A failure never creates
    # another run or rolls back a legitimate owner Start. Native cron recovers.
    token = environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        receipt["status"] = "enqueued_wake_unavailable"
        receipt["wake"] = "failed"
        return receipt
    try:
        wake_status, _ = post(
            _WORKFLOW_DISPATCH,
            # The owner command has already passed the immutable GitHub
            # identity checks and the Control Plane admission transaction.
            # The autonomous runner deliberately requires this existing flag
            # before it will claim a paid Direct work unit on a
            # workflow_dispatch event.  Without it the Start could persist
            # and route a Work Unit, but leave the assigned Direct run until a
            # second, manual workflow dispatch.  This is only a wake hint
            # after commit: Direct still rechecks the durable generation,
            # route, write scopes, cross-repository capability and ledger.
            {"ref": "main", "inputs": {
                "project_key": command.project_key,
                "run_direct": "true",
            }},
            {
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        receipt["wake"] = "requested" if wake_status == 204 else "failed"
    except (error.HTTPError, OSError, TimeoutError):
        receipt["wake"] = "failed"
    if receipt["wake"] != "requested":
        receipt["status"] = "enqueued_wake_unavailable"
    return receipt


def _safe_error(error_code: str) -> dict:
    allowed = {
        "invalid_event_identity", "invalid_command", "control_plane_unavailable",
        "owner_start_migration_not_applied", "control_plane_admission_blocked",
        "invalid_control_plane_receipt",
    }
    return {
        "status": "blocked", "reason": error_code if error_code in allowed else "unverifiable",
        "created": False, "wake": "not_requested", "paid_calls": 0,
        "ready_for_production": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-path", required=True)
    parser.add_argument("--mode", choices=("validate", "enqueue"), required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    receipt = _safe_error("invalid_event_identity")
    exit_code = 2
    try:
        command = read_event(args.event_path, os.environ)
        if args.mode == "validate":
            print("Factory OWNER Start verified before OIDC: " + command.project_key)
            return 0
        receipt = enqueue_owner_start(command, os.environ)
        exit_code = 0 if receipt["status"] in ("enqueued", "replayed") else 3
    except OwnerStartBlocked as exc:
        receipt = _safe_error(exc.code)
    except (ValueError, OSError, RuntimeError):
        receipt = _safe_error("unverifiable")
    if args.output and args.mode == "enqueue":
        Path(args.output).write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
