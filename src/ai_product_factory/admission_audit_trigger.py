"""Owner-only read-only admission diagnostic trigger; no dispatch capability."""
from __future__ import annotations

import os
import re
from typing import Mapping

_KEY = r"[a-z0-9][a-z0-9_-]{0,99}"
_UUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
_COMMENT = re.compile(r"/factory-admission-diagnose (" + _KEY + r")(?: (" + _UUID + r"))?\Z",re.ASCII)
_KEY_RE = re.compile(_KEY + r"\Z",re.ASCII)
_UUID_RE = re.compile(_UUID + r"\Z",re.ASCII)


def resolve_target(env: Mapping[str,str]) -> tuple[str,str]:
    event=env.get("FACTORY_EVENT_NAME","")
    if event=="issue_comment":
        if (env.get("FACTORY_AUTHOR_ASSOCIATION")!="OWNER"
                or env.get("FACTORY_ISSUE_IS_PR")!="false"):
            raise ValueError("not an owner issue comment")
        body=env.get("FACTORY_COMMENT_BODY","")
        if not isinstance(body,str) or len(body.encode("utf-8"))>160:
            raise ValueError("invalid diagnostic comment")
        match=_COMMENT.fullmatch(body)
        if match is None:
            raise ValueError("invalid diagnostic comment syntax")
        key,run=match.groups()
        run=run or ""
    elif event=="workflow_dispatch":
        if (env.get("FACTORY_ADMISSION_ENABLED")!="true"
                or env.get("FACTORY_JOURNEY_ENABLED")=="true"
                or env.get("FACTORY_OFFLINE_ENABLED")=="true"):
            raise ValueError("admission-only run not explicitly selected")
        key=env.get("FACTORY_DISPATCH_PROJECT_KEY","")
        run=env.get("FACTORY_DISPATCH_RUN_ID","")
    else:
        raise ValueError("unsupported admission diagnostic event")
    if not isinstance(key,str) or _KEY_RE.fullmatch(key) is None:
        raise ValueError("invalid project identity")
    if not isinstance(run,str) or (run and _UUID_RE.fullmatch(run) is None):
        raise ValueError("invalid run identity")
    return key,run


def main()->int:
    try:
        key,run=resolve_target(os.environ)
        path=os.environ.get("GITHUB_OUTPUT","")
        if not path:
            raise ValueError("output unavailable")
        with open(path,"a",encoding="utf-8") as f:
            f.write("project_key="+key+"\n")
            f.write("run_id="+run+"\n")
    except (ValueError,TypeError,OSError):
        print("::error::Read-only admission diagnostic command rejected")
        return 2
    print("Read-only admission target verified; workers and models disabled")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
