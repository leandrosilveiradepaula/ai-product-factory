#!/usr/bin/env python3
"""Owner-only exact SHA candidate gate inventory; never dispatches or releases."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib import parse, request

from ai_product_factory.candidate_gate_audit import CandidateGateEvidenceError, observe_candidate_gates
from ai_product_factory.github_rest import GitHubRestAdapter
from ai_product_factory.supabase_server import resolve_supabase_server_config

_REPO="leandrosilveiradepaula/ai-product-factory"
_COMMAND=re.compile(
    r"/factory-candidate-gates ([a-z0-9][a-z0-9_-]{0,99}) "
    r"pr=([1-9][0-9]{0,5}) sha=([0-9a-f]{40})\Z",
    re.ASCII,
)


def validate_event(event: object, *, repository: str) -> tuple[str,int,str]:
    if not isinstance(event,dict) or repository!=_REPO:
        raise ValueError("untrusted event repository")
    src=event.get("repository")
    issue=event.get("issue")
    comment=event.get("comment")
    if (not isinstance(src,dict) or src.get("full_name")!=_REPO
        or not isinstance(issue,dict) or issue.get("number")!=713
        or "pull_request" in issue
        or not isinstance(comment,dict)
        or comment.get("author_association")!="OWNER"):
        raise ValueError("candidate audit is not an owner issue event")
    body=comment.get("body")
    found=_COMMAND.fullmatch(body) if isinstance(body,str) else None
    if not found:
        raise ValueError("invalid exact owner candidate audit command")
    project_key,number,sha=found.groups()
    return project_key,int(number),sha



def _safe_failure_reason(exc: Exception) -> str:
    """Export only reviewed constant error codes, never raw GitHub/CP details."""
    if not isinstance(exc, CandidateGateEvidenceError):
        return "unverifiable_live_evidence"
    return {
        "incomplete changed-file inventory": "changed_file_inventory_incomplete",
        "invalid changed-file provenance": "changed_file_provenance_invalid",
        "invalid renamed-file provenance": "changed_file_provenance_invalid",
        "unexpected previous changed-file path": "changed_file_provenance_invalid",
        "duplicate changed-file provenance": "changed_file_provenance_invalid",
        "candidate identity moved during audit": "candidate_identity_changed",
    }.get(str(exc), "unverifiable_live_evidence")


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="GET-only exact-PR advisory gate inventory")
    parser.add_argument("--event-path",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args(argv)
    result:dict={"status":"blocked","reason_code":"unverifiable_live_evidence",
                 "read_only":True,"writes":0,"paid_calls":0,
                 "ready_for_production":False,"product_ready":False}
    code=2
    try:
        if Path(args.event_path).stat().st_size>128_000:
            raise ValueError("oversized event payload")
        event=json.loads(Path(args.event_path).read_text(encoding="utf-8"))
        key,number,sha=validate_event(event,repository=os.getenv("GITHUB_REPOSITORY",""))
        config=resolve_supabase_server_config()
        def cp_get(path:str):
            req=request.Request(config.url+"/rest/v1/"+path,
                                headers=config.headers,method="GET")
            with request.urlopen(req,timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))

        project_rows=cp_get(
            "factory_projects?select=repository&project_key=eq."
            +parse.quote(key,safe="")+"&limit=2"
        )
        if not isinstance(project_rows,list) or len(project_rows)!=1:
            raise RuntimeError("unverifiable project/repository association")
        repository=project_rows[0].get("repository")
        if not isinstance(repository,str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repository,re.ASCII):
            raise RuntimeError("invalid target repository")
        github=GitHubRestAdapter(repository=repository)
        def github_get(path:str):
            parsed=parse.urlsplit(path)
            if (parsed.scheme or parsed.netloc
                or not parsed.path.startswith("/repos/"+repository+"/")
                and parsed.path!="/repos/"+repository):
                raise ValueError("GitHub GET outside target repository")
            return github._call(
                "GET",parsed.path,
                query=dict(parse.parse_qsl(parsed.query,keep_blank_values=False))
                if parsed.query else None,
            )

        # Browser verifier provenance is checked with this workflow's own
        # repo-scoped GITHUB_TOKEN, never a cross-repo target installation token.
        factory=GitHubRestAdapter(repository=_REPO)
        def factory_get(path:str):
            parsed=parse.urlsplit(path)
            prefix="/repos/"+_REPO+"/actions/runs/"
            if (parsed.scheme or parsed.netloc
                or not re.fullmatch(
                    re.escape(prefix)+r"[1-9][0-9]*(?:/jobs)?",
                    parsed.path, re.ASCII)):
                raise ValueError("GitHub GET outside trusted verifier run path")
            is_jobs=parsed.path.endswith("/jobs")
            if (is_jobs and parsed.query!="per_page=100") or (not is_jobs and parsed.query):
                raise ValueError("unexpected Factory verifier query")
            return factory._call(
                "GET", parsed.path,
                query={"per_page":"100"} if is_jobs else None,
            )

        result=observe_candidate_gates(
            project_key=key,pr_number=number,candidate_sha=sha,
            cp_get=cp_get,github_get=github_get,factory_get=factory_get,
        )
        result["evidence_state"]="observed_exact_candidate"
        code=0
    except Exception as exc:
        # No HTTP bodies or exceptions containing remote sensitive data.
        result["error_type"]=type(exc).__name__
        result["reason_code"]=_safe_failure_reason(exc)
        result["evidence_state"]="insufficient_evidence"
    Path(args.output).write_text(
        json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8",
    )
    print(json.dumps(result,sort_keys=True,ensure_ascii=False))
    return code


if __name__=="__main__":
    sys.exit(main())
