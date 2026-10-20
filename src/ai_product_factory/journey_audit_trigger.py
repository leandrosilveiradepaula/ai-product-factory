"""Owner-only no-model read-only journey audit GitHub trigger.

Supports explicit workflow_dispatch and an exact OWNER comment on an issue.
No arbitrary shell evaluation, production merge, model, queue claim or writes.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Mapping

_PROJECT=re.compile(r"[a-z0-9][a-z0-9-]{1,119}\Z",re.ASCII)
_RUN=re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z",re.ASCII)
_UTC=re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z\Z")
_COMMENT=re.compile(
    r"/factory-journey-audit ([a-z0-9][a-z0-9-]{1,119}) "
    r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}) "
    r"(20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z)\Z",
    re.ASCII,
)
_STAGES=frozenset((
    "none","manual_start","discovery","specification","planning",
    "routing","implementation","review","github_ci","preview",
    "awaiting_release","human_release_observed","operations",
))


def resolve_target(env: Mapping[str,str]) -> tuple[str,str,str,str]:
    event=env.get("FACTORY_EVENT_NAME")
    if event=="issue_comment":
        if (env.get("FACTORY_AUTHOR_ASSOCIATION")!="OWNER"
            or env.get("FACTORY_ISSUE_IS_PR")!="false"):
            raise ValueError("journey audit is not an owner issue command")
        body=env.get("FACTORY_COMMENT_BODY","")
        if not isinstance(body,str) or len(body.encode("utf-8"))>220:
            raise ValueError("invalid owner journey comment")
        matched=_COMMENT.fullmatch(body)
        if matched is None:
            raise ValueError("malformed owner journey comment")
        key,run,since=matched.groups()
        stage="operations"
    elif event=="workflow_dispatch":
        if (env.get("FACTORY_DISPATCH_ENABLED")!="true"
            or env.get("FACTORY_OFFLINE_ENABLED")=="true"):
            raise ValueError("journey audit was not explicitly selected")
        key=env.get("FACTORY_DISPATCH_PROJECT_KEY","")
        run=env.get("FACTORY_DISPATCH_RUN_ID","")
        since=env.get("FACTORY_DISPATCH_SINCE_UTC","")
        stage=env.get("FACTORY_DISPATCH_REQUIRE_STAGE","none") or "none"
    else:
        raise ValueError("unsupported journey audit event")
    if not isinstance(key,str) or not _PROJECT.fullmatch(key):
        raise ValueError("invalid project key")
    if not isinstance(run,str) or (run and not _RUN.fullmatch(run)):
        raise ValueError("invalid run id")
    if event=="issue_comment" and not run:
        raise ValueError("owner audit requires exact run id")
    if not isinstance(since,str) or not _UTC.fullmatch(since):
        raise ValueError("journey audit requires exact UTC cutoff")
    try:
        instant=datetime.strptime(since,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid journey cutoff date") from exc
    if instant>datetime.now(timezone.utc):
        raise ValueError("journey cutoff cannot be in future")
    if stage not in _STAGES:
        raise ValueError("invalid required journey stage")
    return key,run,since,stage


def main() -> int:
    try:
        key,run,since,stage=resolve_target(os.environ)
        path=os.environ.get("GITHUB_OUTPUT")
        if not path:
            raise ValueError("GitHub output unavailable")
        with open(path,"a",encoding="utf-8") as out:
            out.write("project_key="+key+"\n")
            out.write("run_id="+run+"\n")
            out.write("since_utc="+since+"\n")
            out.write("require_stage="+stage+"\n")
    except (OSError,ValueError,TypeError):
        print("::error::Read-only journey audit command rejected")
        return 2
    print("Read-only journey audit target verified; model/worker disabled")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
