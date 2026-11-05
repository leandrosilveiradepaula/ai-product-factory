#!/usr/bin/env python3
"""Trusted single-journey V2 read-only audit. Never starts work or grants release."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from uuid import UUID

from ai_product_factory.github_owner_start import FACTORY_REPO, OWNER_ID, OWNER_LOGIN
from ai_product_factory.native_v2_journey_audit import (
    EvidenceBlocked, audit_existing_native_v2,
)
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader

COMMAND = re.compile(
    r"/factory-v2-journey-audit ([a-z0-9][a-z0-9-]{1,119}) "
    r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\Z", re.ASCII,
)


def resolve_target(*, event: dict, env: dict[str, str]) -> tuple[str, str]:
    if (env.get("GITHUB_REPOSITORY") != FACTORY_REPO
            or env.get("GITHUB_REF") != "refs/heads/main"
            or env.get("GITHUB_ACTOR") != OWNER_LOGIN
            or env.get("GITHUB_EVENT_NAME") not in {"issue_comment", "workflow_dispatch"}
            or not isinstance(event, dict)
            or not isinstance(event.get("sender"), dict)
            or event["sender"].get("login") != OWNER_LOGIN
            or event["sender"].get("id") != OWNER_ID):
        raise EvidenceBlocked("owner_event_identity_invalid")
    if env["GITHUB_EVENT_NAME"] == "issue_comment":
        issue = event.get("issue")
        comment = event.get("comment")
        if (event.get("action") != "created"
                or not isinstance(issue, dict) or issue.get("number") != 713
                or issue.get("pull_request") is not None
                or not isinstance(comment, dict)
                or comment.get("author_association") != "OWNER"
                or not isinstance(comment.get("user"), dict)
                or comment["user"].get("id") != OWNER_ID
                or comment["user"].get("login") != OWNER_LOGIN
                or not isinstance(comment.get("body"), str)
                or len(comment["body"].encode("utf-8")) > 200):
            raise EvidenceBlocked("owner_comment_invalid")
        match = COMMAND.fullmatch(comment["body"])
        if match is None:
            raise EvidenceBlocked("native_v2_command_invalid")
        project_key, journey_id = match.groups()
    else:
        inputs = event.get("inputs")
        if not isinstance(inputs, dict):
            raise EvidenceBlocked("dispatch_inputs_missing")
        project_key, journey_id = inputs.get("project_key"), inputs.get("journey_id")
        if (not isinstance(project_key, str)
                or not isinstance(journey_id, str)
                or COMMAND.fullmatch(
                    "/factory-v2-journey-audit " + project_key + " " + journey_id
                ) is None):
            raise EvidenceBlocked("dispatch_inputs_invalid")
    if str(UUID(journey_id)) != journey_id:
        raise EvidenceBlocked("journey_identity_invalid")
    return project_key, journey_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--check-event", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result: dict
    try:
        if (not args.event_path.is_file()
                or not 0 < args.event_path.stat().st_size <= 131072):
            raise EvidenceBlocked("event_payload_invalid")
        event = json.loads(args.event_path.read_text(encoding="utf-8"))
        key, journey = resolve_target(event=event, env=dict(os.environ))
        if args.check_event:
            print("NATIVE_V2_OWNER_AUDIT_EVENT_VERIFIED")
            return 0
        if args.output is None:
            raise EvidenceBlocked("audit_output_missing")
        result = audit_existing_native_v2(
            reader=SupabaseJourneyReader(), project_key=key, journey_id=journey,
        )
    except EvidenceBlocked as exc:
        result = {"status": "blocked", "reason_code": str(exc),
                  "product_ready": False, "paid_calls": 0, "writes": 0}
    except (OSError, ValueError, RuntimeError, TypeError, KeyError):
        result = {"status": "blocked", "reason_code": "unverifiable_live_evidence",
                  "product_ready": False, "paid_calls": 0, "writes": 0}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("requirement_met") is True else 2


if __name__ == "__main__":
    sys.exit(main())
