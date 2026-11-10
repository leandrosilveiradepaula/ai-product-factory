"""Bind a completed visual capture to the *independently verified* exact CI run.
 
The workflow event is never edited or forged: a separate verifier input is
derived from GitHub API after checking the real trigger and both completed runs.
All independent verifiers still validate the Factory runner and CI job evidence.
"""
from __future__ import annotations

import re
from typing import Callable, Mapping

REPOSITORY="leandrosilveiradepaula/ai-product-factory"
SHA=re.compile(r"[0-9a-f]{40}$")
VISUAL="Authenticated Console visual evidence"
VISUAL_PATH=".github/workflows/authenticated-visual-evidence.yml"
VALIDATION_PATH=".github/workflows/validate.yml"


class VisualCIBindingBlocked(RuntimeError):
    pass


def bind_exact_ci_source(*, repository: str, assessed_commit: str,
                         actual_event: Mapping[str, object],
                         validation_run_id: int,
                         github_get: Callable[[str], object]) -> dict | None:
    if (repository!=REPOSITORY or not isinstance(assessed_commit,str)
            or SHA.fullmatch(assessed_commit) is None
            or not isinstance(actual_event,Mapping)
            or type(validation_run_id) is not int or validation_run_id<=0):
        raise VisualCIBindingBlocked("ci_bridge_input_invalid")
    upstream=actual_event.get("workflow_run")
    if not isinstance(upstream,dict):
        raise VisualCIBindingBlocked("ci_bridge_event_missing")
    if upstream.get("name")=="validate":
        # The existing source verifiers consume the actual CI event and
        # independently verify it. No substitution is needed or allowed.
        return None
    if not all((
        upstream.get("name")==VISUAL,
        upstream.get("path")==VISUAL_PATH,
        upstream.get("event")=="workflow_dispatch",
        upstream.get("head_sha")==assessed_commit,
        upstream.get("head_branch")=="main",
        upstream.get("run_attempt")==1,
        upstream.get("status")=="completed",
        upstream.get("conclusion")=="success",
        isinstance(upstream.get("repository"),dict),
        (upstream.get("repository") or {}).get("full_name")==repository,
        type(upstream.get("id")) is int,
        upstream.get("id",0)>0,
    )):
        raise VisualCIBindingBlocked("ci_bridge_visual_source_unverified")
    prefix="/repos/"+repository
    visual=github_get(prefix+"/actions/runs/"+str(upstream["id"]))
    if not isinstance(visual,dict) or any(
        visual.get(field)!=upstream[field] for field in (
            "id","name","path","event","head_sha","head_branch",
            "run_attempt","status","conclusion"
        )
    ) or (visual.get("repository") or {}).get("full_name")!=repository:
        raise VisualCIBindingBlocked("ci_bridge_visual_run_unbound")
    ci=github_get(prefix+"/actions/runs/"+str(validation_run_id))
    if not isinstance(ci,dict) or not all((
        ci.get("id")==validation_run_id,
        ci.get("name")=="validate",
        ci.get("path")==VALIDATION_PATH,
        ci.get("event")=="push",
        ci.get("head_sha")==assessed_commit,
        ci.get("head_branch")=="main",
        ci.get("run_attempt")==1,
        ci.get("status")=="completed",
        ci.get("conclusion")=="success",
        (ci.get("repository") or {}).get("full_name")==repository,
    )):
        raise VisualCIBindingBlocked("ci_bridge_exact_validation_unverified")
    runs=github_get(prefix+"/actions/runs/"+str(validation_run_id)+"/jobs?per_page=100")
    jobs=runs.get("jobs") if isinstance(runs,dict) else None
    if (not isinstance(jobs,list) or type(runs.get("total_count")) is not int
            or not 1<=len(jobs)<=100 or len(jobs)!=runs["total_count"]):
        raise VisualCIBindingBlocked("ci_bridge_validation_jobs_unavailable")
    valid=set()
    for job in jobs:
        if not isinstance(job,dict) or not all((
            job.get("run_id")==validation_run_id,
            job.get("head_sha")==assessed_commit,
            job.get("status")=="completed",
            job.get("conclusion")=="success",
            isinstance(job.get("name"),str)
        )):
            raise VisualCIBindingBlocked("ci_bridge_validation_jobs_unverified")
        valid.add(job["name"])
    if not {"test","factory-acceptance"}.issubset(valid):
        raise VisualCIBindingBlocked("ci_bridge_required_jobs_missing")
    head=github_get(prefix+"/git/ref/heads/main")
    if not isinstance(head,dict) or (head.get("object") or {}).get("sha")!=assessed_commit:
        raise VisualCIBindingBlocked("ci_bridge_main_moved")
    # Only the trusted independent CI-proof input is derived. No statement
    # about Auth, access, full UX or E2E is made by this bridge.
    return {"workflow_run":ci}
