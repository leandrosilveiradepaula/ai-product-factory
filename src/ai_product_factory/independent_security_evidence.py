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
TRUSTED_SCANNER_SHA = "07fe30d6c7a83614016610ab6b734e16cd306a27"
TRUSTED_SCANNER_FILES = (
 "scripts/audit_block1_complete_tree.py", "scripts/audit_block1_supply_chain.py",
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
 require(isinstance(value,dict) and value.get("schema")=="factory-block1-credential-exposure-v3" and value.get("scope")=="static-import-reachability-for-client-public-health-and-privileged-route-handler-guards-not-runtime-authentication" and type(value.get("console_files_scanned")) is int and value["console_files_scanned"]>0 and type(value.get("client_entrypoints_scanned")) is int and value["client_entrypoints_scanned"]>0 and type(value.get("route_handlers_scanned")) is int and value["route_handlers_scanned"]>0 and value.get("public_surface_roots")==["apps/console/app/api/health/route.ts"] and value.get("credential_exposure_detected") is False and value.get("privileged_values_read") is False and value.get("security_certified") is False and value.get("writes")==0 and value.get("paid_calls")==0 and value.get("findings")==[],"credential_exposure_receipt_invalid")
 return value

def _tree(github_get: Callable[[str],object],prefix: str,sha: str)->tuple[str,int]:
 commit=github_get(prefix+"/git/commits/"+sha); tree=(commit.get("tree") or {}).get("sha") if isinstance(commit,dict) else None; require(isinstance(tree,str) and SHA.fullmatch(tree),"security_commit_tree_invalid")
 listing=github_get(prefix+"/git/trees/"+tree+"?recursive=1"); rows=listing.get("tree") if isinstance(listing,dict) else None; require(isinstance(rows,list) and listing.get("truncated") is False,"security_tree_listing_incomplete")
 blobs=[x for x in rows if isinstance(x,dict) and x.get("type")=="blob"]; require(len(blobs)>=100 and all(isinstance(x.get("path"),str) and isinstance(x.get("sha"),str) and SHA.fullmatch(x["sha"]) for x in blobs),"security_tree_entries_invalid"); return tree,len(blobs)

def _scan_run(github_get: Callable[[str],object],prefix: str,kind: str,tree: str)->tuple[dict,int]:
 workflow_id,workflow_name,job_name,_,_,steps=WORKFLOWS[kind]; listing=github_get(prefix+f"/actions/workflows/{workflow_id}/runs?event=pull_request&status=success&per_page=100"); rows=listing.get("workflow_runs") if isinstance(listing,dict) else None; require(isinstance(rows,list) and 0<len(rows)<=100,"security_scan_run_inventory_invalid")
 matches=[]
 for run in rows:
  if not isinstance(run,dict) or run.get("name")!=workflow_name or run.get("event")!="pull_request" or run.get("status")!="completed" or run.get("conclusion")!="success" or run.get("run_attempt")!=1 or not isinstance(run.get("head_sha"),str) or not SHA.fullmatch(run["head_sha"]): continue
  if _tree(github_get,prefix,run["head_sha"])[0]==tree: matches.append(run)
 require(len(matches)==1,"security_scan_tree_not_unique"); run=matches[0]; run_id=run.get("id"); require(type(run_id)is int and run_id>0,"security_source_run_invalid")
 jobs=github_get(prefix+"/actions/runs/"+str(run_id)+"/jobs?per_page=100"); rows=jobs.get("jobs") if isinstance(jobs,dict) else None
 require(isinstance(rows,list) and jobs.get("total_count")==1 and len(rows)==1 and isinstance(rows[0],dict) and rows[0].get("name")==job_name and rows[0].get("run_id")==run_id and rows[0].get("head_sha")==run["head_sha"] and rows[0].get("status")=="completed" and rows[0].get("conclusion")=="success" and all(any(isinstance(x,dict) and x.get("name")==step and x.get("status")=="completed" and x.get("conclusion")=="success" for x in rows[0].get("steps",[])) for step in steps),"security_source_job_invalid"); return run,run_id

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
  run,run_id=_scan_run(github_get,prefix,kind,tree); _trusted_scanner_source(github_get,prefix,run["head_sha"]); runs[kind]=run_id; _,_,_,artifact_name,member,_=WORKFLOWS[kind]; inventory=github_get(prefix+"/actions/runs/"+str(run_id)+"/artifacts?per_page=100"); artifacts=inventory.get("artifacts") if isinstance(inventory,dict) else None
  require(isinstance(artifacts,list) and inventory.get("total_count")==1 and len(artifacts)==1 and isinstance(artifacts[0],dict),"security_artifact_inventory_invalid"); artifact=artifacts[0]; binding=artifact.get("workflow_run") or {}
  require(artifact.get("name")==artifact_name and artifact.get("expired") is False and type(artifact.get("id")) is int and artifact["id"]>0 and isinstance(artifact.get("digest"),str) and DIGEST.fullmatch(artifact["digest"]) and type(artifact.get("size_in_bytes")) is int and 0<artifact["size_in_bytes"]<=32768 and binding.get("id")==run_id and binding.get("head_sha")==run["head_sha"] and binding.get("head_repository_id")==1387883686,"security_artifact_provenance_invalid")
  raw=archive_fetch(artifact.get("archive_download_url",""),env.get("GITHUB_TOKEN",""),artifact["id"]); receipts[kind]=_receipt(raw,artifact["digest"],kind,member,run["head_sha"],tree,tracked)
  if kind=="gitleaks": receipts["credential_exposure"]=_credential_receipt(raw)
 latest=github_get(prefix+"/git/ref/heads/main"); require(isinstance(latest,dict) and (latest.get("object") or {}).get("sha")==assessed_commit,"security_main_changed_while_verifying")
 return VerifiedCriterionEvidence(domain="security",criterion="secrets_dependencies",repository=repository,assessed_commit=assessed_commit,verification_state="reviewed",source="tree-bound-gitleaks-and-npm:"+tree+":"+":".join(str(runs[x]) for x in sorted(runs)),evidence=("https://github.com/"+repository+"/actions/runs/"+str(current_id)+"#sha="+assessed_commit,),retained_receipt={"tree_oid":tree,"tracked_files":tracked,"gitleaks":receipts["gitleaks"],"credential_exposure":receipts["credential_exposure"],"npm":receipts["npm"]})
