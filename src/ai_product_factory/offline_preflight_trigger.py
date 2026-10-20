"""Owner-only, fail-closed target resolver for read-only offline GitHub preflight.

This module has no transport or worker/model dependencies.
"""
from __future__ import annotations

import os
import re
from typing import Mapping

_KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z", re.ASCII)
_RUN_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z", re.ASCII)
_COMMAND = re.compile(
    r"/factory-offline-preflight ([a-z0-9][a-z0-9-]{0,63}) "
    r"([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\Z", re.ASCII
)


def resolve_target(env: Mapping[str, str]) -> tuple[str, str]:
    """Validate exactly one manual workflow dispatch OR one owner issue comment.

    No fallback between events; reject whitespace, suffixes and invalid types.
    """
    event = env.get("FACTORY_EVENT_NAME", "")
    if event == "workflow_dispatch":
        if env.get("FACTORY_DISPATCH_ENABLED") != "true" or env.get("FACTORY_JOURNEY_ENABLED") == "true":
            raise ValueError("offline preflight was not explicitly selected")
        project = env.get("FACTORY_DISPATCH_PROJECT_KEY", "")
        run = env.get("FACTORY_DISPATCH_RUN_ID", "")
    elif event == "issue_comment":
        if (env.get("FACTORY_AUTHOR_ASSOCIATION") != "OWNER"
                or env.get("FACTORY_ISSUE_IS_PR") != "false"):
            raise ValueError("offline comment is not an owner issue command")
        command = env.get("FACTORY_COMMENT_BODY", "")
        if not isinstance(command, str) or len(command.encode("utf-8")) > 150:
            raise ValueError("offline comment is invalid")
        parsed = _COMMAND.fullmatch(command)
        if parsed is None:
            raise ValueError("offline comment must match exact syntax")
        project, run = parsed.groups()
    else:
        raise ValueError("unsupported offline preflight event")
    if not isinstance(project, str) or _KEY.fullmatch(project) is None:
        raise ValueError("invalid offline project identity")
    if not isinstance(run, str) or _RUN_ID.fullmatch(run) is None:
        raise ValueError("invalid offline run identity")
    return project, run


def main() -> int:
    try:
        project, run = resolve_target(os.environ)
        output_path = os.environ.get("GITHUB_OUTPUT", "")
        if not output_path:
            raise ValueError("GitHub output not configured")
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"project_key={project}\n")
            output.write(f"run_id={run}\n")
    except (OSError, TypeError, ValueError):
        # Sanitized failure: never echo untrusted command body or credentials.
        print("::error::Offline preflight command rejected (identity, scope, or syntax)")
        return 2
    print("Offline read-only target accepted; no worker or model started")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
