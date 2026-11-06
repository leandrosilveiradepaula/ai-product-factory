"""Read-only operational-document preflight; never a readiness attestation."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

REQUIRED = {
    "docs/OPERATIONS.md": ("Contrato de finalização", "product_ready=false", "não executar"),
    "docs/RELEASE_AUTONOMY.md": ("humano", "auto-merge", "rollback"),
    "docs/FINALIZATION_EXECUTION_CONTRACT.md": ("produção", "evidência", "não executar"),
}

def audit(root: Path) -> dict:
    root = root.resolve(strict=True); inventory = []
    for relative, markers in REQUIRED.items():
        path = root / relative
        if not path.is_file() or path.is_symlink(): raise ValueError("required runbook unavailable")
        body = path.read_text(encoding="utf-8")
        inventory.append({"path": relative, "sha256": hashlib.sha256(body.encode()).hexdigest(), "markers_present": all(x.casefold() in body.casefold() for x in markers)})
    return {"schema":"factory-certification-operations-preflight-v1", "scope":"runbook-contract-review-not-live-recovery", "runbooks":inventory, "all_contract_markers_present":all(x["markers_present"] for x in inventory), "environment_queries_executed":0, "production_writes":0, "paid_calls":0, "operations_certified":False}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]); parser.add_argument("--output",type=Path)
    args=parser.parse_args(); result=audit(args.root)
    if args.output: args.output.write_text(json.dumps(result,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True)); raise SystemExit(0 if result["all_contract_markers_present"] else 1)
