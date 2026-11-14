"""Fail-closed, tree-bound Gitleaks and dependency evidence."""
from __future__ import annotations
import hashlib, io, json, os, re, urllib.error, urllib.parse, urllib.request, zipfile
from collections.abc import Callable, Mapping
from .product_readiness_certification import VerifiedCriterionEvidence

REPO = "leandrosilveiradepaula/ai-product-factory"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z", re.ASCII)
WORKFLOWS = {
 "gitleaks": (408870557, "Block 1 independent secret scanner", "gitleaks", "block1-full-tree-gitleaks", "block1-full-tree-scan-receipt.json", ("Scan PR/history with independent Gitleaks engine", "Scan complete exact commit tree independently of PR diff")),
 "npm": (408663891, "Block 1 independent dependency advisory evidence", "npm-production-advisories", "block1-npm-advisories", "block1-npm-audit-summary.json", ("Scan exact production lockfile without package installation",)),
}
REVIEWED_FIXTURES = frozenset({
 ("supabase/functions/factory-runtime-control-plane/index.ts",142,"private-key"),
 ("tests/test_reconciled_candidate_delivery.py",63,"generic-api-key"),("tests/test_reconciled_candidate_delivery.py",82,"generic-api-key"),
 ("tests/test_repair_runtime.py",12,"generic-api-key"),("tests/test_repository_snapshot_safety.py",97,"generic-api-key"),
 ("tests/test_specialist_traceability_atomicity.py",24,"generic-api-key"),("tests/test_followup_execution_epochs.py",178,"generic-api-key"),("tests/test_specialist_epoch_fence.py",71,"generic-api-key"),
})
# Human-merged main SHA after #1371. The only scanner-source change vs the
# prior trusted ref is Windows fixture launch / strict resolved repository path;
# the actual Gitleaks rules, receipt contract and other four protected sources
# remain byte-identical. Never use a moving branch as a trust anchor.
TRUSTED_SCANNER_SHA = "3078063a3936e6d73fa9816fd0293881c394a19a"
TRUSTED_SCANNER_FILES = (
 "scripts/audit_block1_complete_tree.py", "scripts/audit_block1_supply_chain.py",
 "scripts/audit_block1_credential_exposure.py",
 ".github/workflows/block1-independent-secrets.yml",
 ".github/workflows/block1-independent-dependency-audit.yml",
)
class SecurityEvidenceBlocked(RuntimeError): pass
def require(value: bool, code: str) -> None:
 if not value: raise SecurityEvidenceBlocked(code)
class _NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def _download(url: str, token: str, artifact_id: int) -> bytes:
 expected=f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact_id}/zip"; require(url==expected and bool(token),"security_artifact_source_invalid")
 request=urllib.request.Request(expected,headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token})
 try:
  with urllib.request.build_opener(_NoRedirect).open(request,timeout=25) as response: raw=response.read(32769)
 except urllib.error.HTTPError as exc:
  require(exc.code in (301,302,303,307,308),"security_artifact_download_denied"); target=urllib.parse.urlsplit(exc.headers.get("Location", "")); host=(target.hostname or "").lower()
  require(target.scheme=="https" and not target.username and not target.password and (host.endswith(".blob.core.windows.net") or host.endswith(".actions.githubusercontent.com") or host=="pipelines.actions.githubusercontent.com"),"security_artifact_redirect_untrusted")
  with urllib.request.urlopen(urllib.request.Request(target.geturl(),headers={"Accept":"application/zip"}),timeout=25) as response: raw=response.read(32769)
 require(0<len(raw)<=32768,"security_artifact_size_invalid"); return raw

def _receipt(raw: bytes,digest: str,kind: str,member: str,sha: str,tree: str,tracked: int)->dict:
 require(digest=="sha256:"+hashlib.sha256(raw).hexdigest(),"security_artifact_digest_invalid")
 try:
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   rows=archive.infolist(); require(0<len(rows)<=2 and any(x.filename==member and 0<x.file_size<=16384 for x in rows),"security_archive_members_invalid"); value=json.loads(archive.read(member).decode("utf-8"))
 except (zipfile.BadZipFile,OSError,UnicodeError,ValueError) as exc: raise SecurityEvidenceBlocked("security_archive_unreadable") from exc
 require(isinstance(value,dict),"security_receipt_invalid")
 if kind=="gitleaks":
  inventory=value.get("reviewed_source_blob_pinned_fixtures")
  observed={(x.get("path"),x.get("line"),x.get("rule_id")) for x in inventory} if isinstance(inventory,list) and all(isinstance(x,dict) and set(x)=={"path","line","rule_id"} and isinstance(x.get("path"),str) and type(x.get("line")) is int and isinstance(x.get("rule_id"),str) for x in inventory) else set()
  require(value.get("schema")=="factory-block1-complete-tracked-tree-gitleaks-v1" and value.get("assessed_commit")==sha and value.get("tree_oid")==tree and value.get("source_digest")==hashlib.sha256((sha+":"+tree).encode()).hexdigest() and value.get("scanner")=="gitleaks" and value.get("scanner_version")=="8.24.3" and value.get("scope")=="complete_committed_tree_not_all_historical_git_commits" and type(value.get("tracked_files_scanned")) is int and value["tracked_files_scanned"]==tracked and tracked>=100 and value.get("scan_passed") is True and value.get("zero_unreviewed_findings") is True and value.get("trusted_builtin_rules") is True and value.get("repository_allowlists_ignored") is True and value.get("raw_finding_count")==len(REVIEWED_FIXTURES) and observed==REVIEWED_FIXTURES and value.get("all_history_scanned") is False and value.get("secrets_dependencies_certified") is False and value.get("block1_certified") is False and value.get("paid_calls")==0 and value.get("production_writes")==0,"security_gitleaks_receipt_scope_invalid")
 else:
  require(value.get("schema")=="factory-block1-npm-advisory-evidence-v1" and value.get("sha")==sha and value.get("scope")=="production_dependencies_lockfile" and value.get("scanner")=="npm audit" and value.get("valid_report") is True and value.get("passed") is True and value.get("high")==0 and value.get("critical")==0 and value.get("scanner_exit_code")==0 and value.get("block1_certified") is False,"security_npm_receipt_scope_invalid")
 return value

def _credential_receipt(raw: bytes)->dict:
 try:
  with zipfile.ZipFile(io.BytesIO(raw)) as archive: value=json.loads(archive.read("block1-credential-exposure-receipt.json").decode("utf-8"))
 except (KeyError,zipfile.BadZipFile,OSError,UnicodeError,ValueError) as exc: raise SecurityEvidenceBlocked("credential_exposure_receipt_unavailable") from exc
 require(isinstance(value,dict) and value.get("schema")=="factory-block1-credential-exposure-v4" and value.get("scope")=="static-import-reachability-for-client-public-health-and-per-http-handler-guards-not-runtime-authentication" and type(value.get("console_files_scanned")) is int and value["console_files_scanned"]>0 and type(value.get("client_entrypoints_scanned")) is int and value["client_entrypoints_scanned"]>0 and type(value.get("route_handlers_scanned")) is int and value["route_handlers_scanned"]>0 and value.get("public_surface_roots")==["apps/console/app/api/health/route.ts"] and value.get("credential_exposure_detected") is False and value.get("privileged_values_read") is False and value.get("security_certified") is False and value.get("writes")==0 and value.get("paid_calls")==0 and value.get("findings")==[],"credential_exposure_receipt_invalid")
 return value

def _tree(github_get: Callable[[str],object],prefix: str,sha: str)->tuple[str,int]:
 commit=github_get(prefix+"/git/commits/"+sha); tree=(commit.get("tree") or {}).get("sha") if isinstance(commit,dict) else None; require(isinstance(tree,str) and SHA.fullmatch(tree),"security_commit_tree_invalid")
 listing=github_get(prefix+"/git/trees/"+tree+"?recursive=1"); rows=listing.get("tree") if isinstance(listing,dict) else None; require(isinstance(rows,list) and listing.get("truncated") is False,"security_tree_listing_incomplete")
 blobs=[x for x in rows if isinstance(x,dict) and x.get("type")=="blob"]; require(len(blobs)>=100 and all(isinstance(x.get("path"),str) and isinstance(x.get("sha"),str) and SHA.fullmatch(x["sha"]) for x in blobs),"security_tree_entries_invalid"); return tree,len(blobs)

def _scan_run(github_get: Callable[[str], object], prefix: str, kind: str,
              tree: str, assessed_commit: str) -> tuple[dict, int]:
  workflow_id, workflow_name, job_name, _, _, steps = WORKFLOWS[kind]
  listing = github_get(prefix + f"/actions/workflows/{workflow_id}/runs"
                       "?event=pull_request&status=success&per_page=100")
  rows = listing.get("workflow_runs") if isinstance(listing, dict) else None
  require(isinstance(rows, list) and 0 < len(rows) <= 100,
          "security_scan_run_inventory_invalid")

  def valid(run: object) -> bool:
    return (
      isinstance(run, dict)
      and run.get("name") == workflow_name
      and run.get("event") == "pull_request"
      and run.get("status") == "completed"
      and run.get("conclusion") == "success"
      and run.get("run_attempt") == 1
      and isinstance(run.get("head_sha"), str)
      and SHA.fullmatch(run["head_sha"]) is not None
    )

  # The human GitHub merge has an exact second-parent PR candidate. Start
  # from THAT immutable identity, not a 100-run scan with a recursive Git
  # tree download for every unrelated PR. This both removes provider overload
  # (HTTP 502 in real post-CI #43434137012) and rejects a scanner from an
  # unrelated same-tree branch. Keep legacy single-source support only for a
  # valid non-merge commit / older offline fixtures.
  merged = github_get(prefix + "/git/commits/" + assessed_commit)
  parents = merged.get("parents") if isinstance(merged, dict) else None
  exact_parent = None
  if parents is not None:
    require(isinstance(parents, list) and len(parents) in (1, 2)
            and all(isinstance(p, dict)
                    and isinstance(p.get("sha"), str)
                    and SHA.fullmatch(p["sha"]) is not None for p in parents)
            and len({p["sha"] for p in parents}) == len(parents),
            "security_merge_parent_provenance_invalid")
    if len(parents) == 2:
      exact_parent = parents[1]["sha"]
  if exact_parent is not None:
    matches = [run for run in rows if valid(run) and
               run["head_sha"] == exact_parent]
    # GitHub can execute multiple PR checks for the very same immutable head
    # (for example after a branch rename). No other SHA may be admitted.
    # Audit EVERY successful exact-head job; only then choose the latest
    # immutable run as the artifact source. Invalid/duplicate IDs fail closed.
    require(0 < len(matches) <= 8
            and all(type(row.get("id")) is int and row["id"] > 0
                    and row.get("head_sha") == exact_parent for row in matches)
            and len({row["id"] for row in matches}) == len(matches),
            "security_scan_parent_sources_invalid")
    # The candidate's complete committed tree must still equal the assessed
    # merge tree. No inference from matching commit labels alone.
    require(_tree(github_get, prefix, exact_parent)[0] == tree,
            "security_scan_parent_tree_mismatch")
  else:
    # Non-merge histories retain the previous conservative selection. This
    # path cannot accept duplicate same-tree scans without a verified second
    # parent, exactly as before.
    matches = [run for run in rows if valid(run) and
               _tree(github_get, prefix, run["head_sha"])[0] == tree]
    require(len(matches) == 1, "security_scan_tree_not_unique")

  # An exact-head duplicate is NOT a second source revision. Both real
  # workflows must have executed the approved scan steps successfully;
  # selecting one without checking its siblings would hide contradictory
  # or counterfeit source jobs.
  for source in matches:
    rid = source.get("id")
    require(type(rid) is int and rid > 0, "security_source_run_invalid")
    try:
      jobs = github_get(prefix + "/actions/runs/" + str(rid)
                        + "/jobs?per_page=100")
    except (KeyError, ValueError, OSError, urllib.error.HTTPError) as exc:
      raise SecurityEvidenceBlocked("security_source_job_unavailable") from exc
    job_rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(isinstance(job_rows, list)
            and jobs.get("total_count") == 1
            and len(job_rows) == 1 and isinstance(job_rows[0], dict)
            and job_rows[0].get("name") == job_name
            and job_rows[0].get("run_id") == rid
            and job_rows[0].get("head_sha") == source["head_sha"]
            and job_rows[0].get("status") == "completed"
            and job_rows[0].get("conclusion") == "success"
            and all(any(isinstance(step, dict)
                        and step.get("name") == expected
                        and step.get("status") == "completed"
                        and step.get("conclusion") == "success"
                        for step in job_rows[0].get("steps", []))
                    for expected in steps),
            "security_source_job_invalid")
  run = max(matches, key=lambda source: source["id"])
  return run, run["id"]


def _trusted_scanner_source(github_get: Callable[[str],object],prefix: str,sha: str)->None:
 for path in TRUSTED_SCANNER_FILES:
  trusted=github_get(prefix+"/contents/"+path+"?ref="+TRUSTED_SCANNER_SHA); candidate=github_get(prefix+"/contents/"+path+"?ref="+sha)
  require(isinstance(trusted,dict) and isinstance(candidate,dict) and isinstance(trusted.get("sha"),str) and SHA.fullmatch(trusted["sha"]) and trusted.get("sha")==candidate.get("sha") and type(trusted.get("size")) is int and trusted.get("size")==candidate.get("size") and trusted["size"]>0,"security_scanner_source_drift")

def verify_existing_secrets_dependencies(*,repository: str,assessed_commit: str,github_get: Callable[[str],object],archive_fetch: Callable[[str,str,int],bytes]=_download,environment: Mapping[str,str]|None=None)->VerifiedCriterionEvidence:
 env=os.environ if environment is None else environment; require(repository==REPO and isinstance(assessed_commit,str) and SHA.fullmatch(assessed_commit) and env.get("GITHUB_ACTIONS")=="true" and env.get("GITHUB_REPOSITORY")==REPO and env.get("GITHUB_EVENT_NAME")=="workflow_run" and env.get("GITHUB_REF")=="refs/heads/main" and env.get("GITHUB_WORKFLOW_REF")==REPO+"/"+OWNER_WORKFLOW+"@refs/heads/main","security_runner_identity_invalid")
 current_id=env.get("GITHUB_RUN_ID",""); require(current_id.isdecimal(),"security_current_run_invalid"); prefix="/repos/"+REPO; current=github_get(prefix+"/actions/runs/"+current_id)
 require(isinstance(current,dict) and current.get("id")==int(current_id) and current.get("name")=="Factory autonomous runner" and current.get("path")==OWNER_WORKFLOW and current.get("event")=="workflow_run" and current.get("head_sha")==assessed_commit and current.get("head_branch")=="main" and current.get("run_attempt")==1,"security_current_runner_unbound")
 main=github_get(prefix+"/git/ref/heads/main"); require(isinstance(main,dict) and (main.get("object") or {}).get("sha")==assessed_commit,"security_main_drift"); tree,tracked=_tree(github_get,prefix,assessed_commit); receipts={}; runs={}
 for kind in WORKFLOWS:
  run,run_id=_scan_run(github_get,prefix,kind,tree,assessed_commit); _trusted_scanner_source(github_get,prefix,run["head_sha"]); runs[kind]=run_id; _,_,_,artifact_name,member,_=WORKFLOWS[kind]; inventory=github_get(prefix+"/actions/runs/"+str(run_id)+"/artifacts?per_page=100"); artifacts=inventory.get("artifacts") if isinstance(inventory,dict) else None
  require(isinstance(artifacts,list) and inventory.get("total_count")==1 and len(artifacts)==1 and isinstance(artifacts[0],dict),"security_artifact_inventory_invalid"); artifact=artifacts[0]; binding=artifact.get("workflow_run") or {}
  require(artifact.get("name")==artifact_name and artifact.get("expired") is False and type(artifact.get("id")) is int and artifact["id"]>0 and isinstance(artifact.get("digest"),str) and DIGEST.fullmatch(artifact["digest"]) and type(artifact.get("size_in_bytes")) is int and 0<artifact["size_in_bytes"]<=32768 and binding.get("id")==run_id and binding.get("head_sha")==run["head_sha"] and binding.get("head_repository_id")==1387883686,"security_artifact_provenance_invalid")
  raw=archive_fetch(artifact.get("archive_download_url",""),env.get("GITHUB_TOKEN",""),artifact["id"]); receipts[kind]=_receipt(raw,artifact["digest"],kind,member,run["head_sha"],tree,tracked)
  if kind=="gitleaks": receipts["credential_exposure"]=_credential_receipt(raw)
 latest=github_get(prefix+"/git/ref/heads/main"); require(isinstance(latest,dict) and (latest.get("object") or {}).get("sha")==assessed_commit,"security_main_changed_while_verifying")
 return VerifiedCriterionEvidence(domain="security",criterion="secrets_dependencies",repository=repository,assessed_commit=assessed_commit,verification_state="reviewed",source="tree-bound-gitleaks-and-npm:"+tree+":"+":".join(str(runs[x]) for x in sorted(runs)),evidence=("https://github.com/"+repository+"/actions/runs/"+str(current_id)+"#sha="+assessed_commit,),retained_receipt={"tree_oid":tree,"tracked_files":tracked,"gitleaks":receipts["gitleaks"],"credential_exposure":receipts["credential_exposure"],"npm":receipts["npm"]})
