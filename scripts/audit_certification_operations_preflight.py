"""Read-only operational-document preflight; never a readiness attestation."""
from __future__ import annotations
import argparse, hashlib, json, os, re, urllib.request
from pathlib import Path

REQUIRED = {
    "docs/OPERATIONS.md": ("Contrato de finalização", "product_ready=false", "não executar"),
    "docs/RELEASE_AUTONOMY.md": ("humano", "auto-merge", "rollback"),
    "docs/FINALIZATION_EXECUTION_CONTRACT.md": ("produção", "evidência", "não executar"),
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
SCHEDULED_RUNS = "/actions/workflows/autonomous-runner.yml/runs?event=schedule&status=success&per_page=20"

def audit(root: Path, *, repository: str = "", github_get=None) -> dict:
    root = root.resolve(strict=True); inventory = []
    for relative, markers in REQUIRED.items():
        path = root / relative
        if not path.is_file() or path.is_symlink(): raise ValueError("required runbook unavailable")
        body = path.read_text(encoding="utf-8")
        inventory.append({"path": relative, "sha256": hashlib.sha256(body.encode()).hexdigest(), "markers_present": all(x.casefold() in body.casefold() for x in markers)})
    live = {"queried": False, "status": "not_requested"}
    queries = 0
    if github_get is not None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid repository")
        prefix = "/repos/" + repository
        main = github_get(prefix + "/git/ref/heads/main")
        runs = github_get(prefix + SCHEDULED_RUNS)
        queries = 2
        sha = (main.get("object") or {}).get("sha") if isinstance(main, dict) else None
        rows = runs.get("workflow_runs") if isinstance(runs, dict) else None
        if not SHA.fullmatch(sha or "") or not isinstance(rows, list) or not rows:
            live = {"queried": True, "status": "unverified"}
        else:
            latest = rows[0]
            valid = isinstance(latest, dict) and latest.get("event") == "schedule" and latest.get("status") == "completed" and latest.get("conclusion") == "success" and latest.get("head_branch") == "main" and SHA.fullmatch(latest.get("head_sha") or "") and type(latest.get("id")) is int
            live = {"queried": True, "status": "scheduled_runner_observed" if valid else "unverified", "main_sha": sha, "scheduled_run_id": latest.get("id") if valid else None, "scheduled_run_sha": latest.get("head_sha") if valid else None}
    return {"schema":"factory-certification-operations-preflight-v2", "scope":"runbook-contract-and-read-only-scheduled-runner-observation-not-live-recovery", "runbooks":inventory, "all_contract_markers_present":all(x["markers_present"] for x in inventory), "live_scheduler":live, "environment_queries_executed":queries, "production_writes":0, "paid_calls":0, "operations_certified":False}

def _github_get(repository: str, token: str):
    def get(path: str):
        request=urllib.request.Request("https://api.github.com"+path,headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,"User-Agent":"factory-operations-preflight"})
        with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)
    return get

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]); parser.add_argument("--output",type=Path); parser.add_argument("--repository",default=os.environ.get("GITHUB_REPOSITORY", "")); parser.add_argument("--observe-github",action="store_true")
    args=parser.parse_args(); token=os.environ.get("GITHUB_TOKEN", ""); result=audit(args.root,repository=args.repository,github_get=_github_get(args.repository,token) if args.observe_github and token else None)
    if args.output: args.output.write_text(json.dumps(result,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True)); raise SystemExit(0 if result["all_contract_markers_present"] else 1)
