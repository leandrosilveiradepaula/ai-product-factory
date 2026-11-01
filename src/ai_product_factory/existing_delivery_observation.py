"""Read-only, bounded evidence of an ALREADY merged issue-related code candidate.

This is only triage, NEVER proof of delivery, successful QA or authorization
to repin a V2 binding. Failed/disconnected GitHub searches return no candidate,
not a fabricated source. One verified, unique code PR is required.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_-]{0,120}\Z")


def inspect_prior_merged_delivery(
    github: object, *, issue_number: int, source_sha: str,
    source_evidence: object,
) -> dict | None:
    repo=getattr(github,"repository",None)
    if (not isinstance(repo,str) or not _REPO.fullmatch(repo)
        or type(issue_number) is not int or not 1<=issue_number<=9999999
        or not isinstance(source_sha,str) or not _SHA.fullmatch(source_sha)
        or not isinstance(source_evidence,Mapping)
        or source_evidence.get("assessed_commit")!=source_sha):
        return None
    inspected=source_evidence.get("inspected_files")
    if (not isinstance(inspected,list) or not inspected or len(inspected)>4
        or source_evidence.get("omitted_paths")
        or any(not isinstance(f,Mapping) or f.get("complete") is not True
               or f.get("assessed_commit")!=source_sha
               or not isinstance(f.get("path"),str) or not f["path"].startswith(("src/","test/","tests/"))
               for f in inspected)):
        return None
    relevant={f["path"] for f in inspected}
    try:
        search=github._call("GET","/search/issues",query={
            "q":f'repo:{repo} is:pr is:merged in:body "Issue #{issue_number}"',
            "per_page":"10",
        })
        if (not isinstance(search,dict) or type(search.get("total_count")) is not int
            or not 1<=search["total_count"]<=10 or
            not isinstance(search.get("items"),list)
            or len(search["items"])!=search["total_count"]):
            return None
        matched=[]
        for entry in search["items"]:
            if not isinstance(entry,dict) or "pull_request" not in entry:
                continue
            body=entry.get("body")
            number=entry.get("number")
            if (not isinstance(body,str) or len(body)>16000
                or not re.search(r"(?<![0-9])(?:issue\s*)#"+str(issue_number)+r"\b",body,re.I)
                or type(number) is not int or number<1):
                continue
            pr=github.get_pull_request(number)
            if (pr.number!=number or pr.merged is not True
                or pr.state!="closed" or pr.head_repository!=repo
                or not isinstance(pr.merge_commit_sha,str)
                or not _SHA.fullmatch(pr.merge_commit_sha)
                or not isinstance(pr.head_sha,str) or not _SHA.fullmatch(pr.head_sha)
                or not isinstance(pr.base_ref,str) or not _BRANCH.fullmatch(pr.base_ref)
                or pr.base_ref in ("main","master") and pr.merge_commit_sha==source_sha):
                continue
            files=github.get_pull_request_files(number)
            if (not isinstance(files,tuple) or not 1<=len(files)<=3000):
                return None
            overlap=sorted(relevant.intersection(files))
            if not overlap:
                continue  # Pure governance/docs PR is never a code delivery.
            branch_head=github.get_branch_sha(pr.base_ref)
            if not isinstance(branch_head,str) or not _SHA.fullmatch(branch_head):
                continue
            lineage=github.compare_commits(pr.merge_commit_sha,branch_head)
            if (not isinstance(lineage,dict)
                or lineage.get("status") not in ("ahead","identical")
                or type(lineage.get("ahead_by")) is not int
                or not 0<=lineage["ahead_by"]<=10000
                or lineage.get("behind_by")!=0):
                continue
            # The relevant code must differ from the frozen source; same bytes
            # cannot demonstrate any change, much less a completed fix.
            if not any(
                github.get_file_text(path,ref=source_sha)
                !=github.get_file_text(path,ref=branch_head)
                for path in overlap
            ):
                continue
            if github.get_branch_sha(pr.base_ref)!=branch_head:
                return None
            matched.append({
                "pr_number":number,"pr_merge_commit":pr.merge_commit_sha,
                "candidate_ref":pr.base_ref,"candidate_sha":branch_head,
                "matched_files":overlap,
            })
        if len(matched)!=1:
            return None  # Ambiguity is not evidence.
        return {
            "status":"existing_delivery_candidate_unverified",
            "repository":repo,"issue_number":issue_number,
            "original_source_sha":source_sha,
            **matched[0],
            "source_binding_unchanged":True,
            "ci_verified":False,"release_authorized":False,
            "product_ready":False,
        }
    except (ValueError, KeyError, TypeError, RuntimeError, OSError, AttributeError):
        return None
