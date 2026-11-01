"""Fail-closed, per-journey acknowledgement of a merged governance-only PR.

An amendment changes *authorization evidence*, never the frozen code source,
journey binding, write scopes, release policy or protected main. The same
evidence must be independently rechecked before Direct writes and integration.
"""
from __future__ import annotations

import hashlib
import re

from .journey_delivery_binding import JourneyBinding

_SHA=re.compile(r"[0-9a-f]{40}\Z")
_EXACT_PATH=re.compile(r"(?:src|app|apps|packages|test|tests)/[A-Za-z0-9_./()\-]+\.(?:tsx?|jsx?|py)\Z")
_GOVERNANCE="docs/codex/CURRENT_TASK.md"


def verify_scoped_governance_amendment(
    *, github:object, binding:JourneyBinding, amendment:object,
    change_set_id:str, observed_ref_sha:str,
) -> dict:
    """Return a bounded audit proof; never trust a Control Plane PR assertion alone.

    This exception to frozen-main HEAD equality is limited to a single merged
    commit containing *only* CURRENT_TASK.md. Code is always read, executed and
    committed from binding.source_commit, not from the moved main.
    """
    def deny()->None:
        raise PermissionError("V2 governance amendment missing, stale or outside scope")

    if (binding.source_mode!="main_snapshot" or binding.source_ref!="main"
        or not isinstance(amendment,dict) or not isinstance(change_set_id,str)
        or not re.fullmatch(r"[0-9a-f-]{36}",change_set_id)
        or not isinstance(observed_ref_sha,str) or not _SHA.fullmatch(observed_ref_sha)
        or observed_ref_sha==binding.source_commit
        or getattr(github,"repository",None)!=binding.repository):
        deny()
    required={
        "version","pr_number","issue_number","source_commit","merge_commit",
        "journey_id","request_id","change_set_id","run_id","work_unit_id",
    }
    if (set(amendment)!=required or type(amendment["version"]) is not int
        or amendment["version"]!=1
        or type(amendment["pr_number"]) is not int or amendment["pr_number"]<1
        or type(amendment["issue_number"]) is not int or amendment["issue_number"]<1
        or amendment["source_commit"]!=binding.source_commit
        or amendment["merge_commit"]!=observed_ref_sha
        or amendment["journey_id"]!=binding.journey_id
        or amendment["request_id"]!=binding.request_id
        or amendment["change_set_id"]!=change_set_id
        or not isinstance(amendment["run_id"],str) or not amendment["run_id"]
        or not isinstance(amendment["work_unit_id"],str) or not amendment["work_unit_id"]):
        deny()
    pr=github.get_pull_request(amendment["pr_number"])
    if (pr.merged is not True or pr.state!="closed" or pr.base_ref!="main"
        or pr.base_sha!=binding.source_commit
        or pr.merge_commit_sha!=observed_ref_sha
        or pr.head_repository!=binding.repository
        or not isinstance(pr.head_sha,str) or not _SHA.fullmatch(pr.head_sha)):
        deny()
    diff=github.compare_commits(binding.source_commit,observed_ref_sha)
    if (not isinstance(diff,dict) or diff.get("status")!="ahead"
        or diff.get("ahead_by")!=1 or diff.get("behind_by")!=0
        or diff.get("files")!=[_GOVERNANCE]
        or github.get_pull_request_files(amendment["pr_number"])!=(_GOVERNANCE,)):
        deny()
    old=github.get_file_text(_GOVERNANCE,ref=binding.source_commit)
    new=github.get_file_text(_GOVERNANCE,ref=observed_ref_sha)
    if (not isinstance(old,str) or not isinstance(new,str) or not new.startswith("# CURRENT_TASK")
        or new==old or len(new)>32000):
        deny()
    first_section=new.split("\n---",1)[0]
    if not re.search(r"^# CURRENT_TASK[^\n]*#"+str(amendment["issue_number"])+r"\b",first_section):
        deny()
    approved=[]
    for raw in re.findall(r"(?m)^-\s+`([^`]+)`",first_section):
        path=raw.strip()
        if not _EXACT_PATH.fullmatch(path):
            continue  # Broad test/documentation patterns are NOT authorization.
        if any(p in (".","..") for p in path.split("/")) or "//" in path:
            deny()
        if path not in approved:
            approved.append(path)
    if not 1<=len(approved)<=12:
        deny()
    if github.get_branch_sha("main")!=observed_ref_sha:
        deny()
    return {
        "kind":"merged_document_only_task_scope_v1","version":1,
        "pr_number":amendment["pr_number"],"issue_number":amendment["issue_number"],
        "source_commit":binding.source_commit,"merge_commit":observed_ref_sha,
        "journey_id":binding.journey_id,"request_id":binding.request_id,
        "change_set_id":change_set_id,"run_id":amendment["run_id"],
        "work_unit_id":amendment["work_unit_id"],
        "authorized_paths":approved,
        "amended_document_sha256":hashlib.sha256(new.encode()).hexdigest(),
        "amended_task_section":first_section[:10000],
        "scope":"documentation-only authorization; code source remains immutable",
    }


def constrain_scoped_amendment(*,source:dict,proof:dict,run_id:str,work_unit_id:str)->dict:
    """Narrow, never expand, plan scopes to verified issue-local exact files."""
    if (proof.get("run_id")!=run_id or proof.get("work_unit_id")!=work_unit_id
        or not isinstance(source.get("journey_request"),dict)):
        raise PermissionError("V2 amendment work unit does not match durable request")
    text=source["journey_request"].get("text")
    issue=proof["issue_number"]
    if (not isinstance(text,str)
        or not re.search(r"(?:issue\s*)#"+str(issue)+r"\b",text,re.IGNORECASE)):
        raise PermissionError("V2 amendment issue does not match the Start request")
    assignment=source.get("assignment")
    scopes=assignment.get("scope_keys") if isinstance(assignment,dict) else None
    if not isinstance(scopes,list) or not scopes:
        raise PermissionError("V2 amendment has no frozen plan scopes")
    approved=set(proof["authorized_paths"])
    exact=[p for p in scopes if isinstance(p,str) and p in approved]
    if not exact:
        raise PermissionError("V2 amendment does not authorize any planned exact file")
    enriched=dict(source)
    enriched["assignment"]={**assignment,"scope_keys":exact}
    enriched["verified_governance_amendment"]=proof
    enriched["human_decisions"]=[
        *(source.get("human_decisions") if isinstance(source.get("human_decisions"),list) else []),
        {
            "decision_kind":"verified_merged_task_scope",
            "response":"The merged, GitHub-verified task-specific CURRENT_TASK authorization applies only to "
                       f"issue #{issue} and exact files {', '.join(exact)}; AGENTS.md, "
                       "security and production gates remain authoritative.",
            "governance_pr":proof["pr_number"],
            "journey_id":proof["journey_id"],
            "authorized_paths":exact,
        },
    ]
    enriched["constraints"]=[
        *(source.get("constraints") if isinstance(source.get("constraints"),list) else []),
        "A verified issue-specific governance amendment supersedes stale task-only "
        "CURRENT_TASK instructions for precisely the approved files. All "
        "permanent AGENTS and human release gates remain binding.",
        "A document-only merge after the frozen source does not rebase "
        "the frozen code SHA or authorize edits to CURRENT_TASK.md.",
    ]
    return enriched
