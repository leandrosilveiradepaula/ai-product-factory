"""Adversarial static guard: simulation labels cannot be release authority."""
from __future__ import annotations
import argparse, ast, json
from pathlib import Path

FORBIDDEN = ("mock", "fixture", "dry_run", "demo", "noop")
RELEASE = "src/ai_product_factory/runtime_cli.py"

def audit(root: Path) -> dict:
    root=root.resolve(strict=True); path=root/RELEASE
    if not path.is_file() or path.is_symlink(): raise ValueError("release runtime unavailable")
    tree=ast.parse(path.read_text(encoding="utf-8"), filename=RELEASE)
    violations=[]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value,str) and any(x in node.value.casefold() for x in FORBIDDEN):
            violations.append(node.lineno)
    return {"schema":"factory-mock-release-boundary-v1", "scope":"release-runtime-literal-guard-not-reachability-proof", "release_runtime":RELEASE, "simulation_marker_literals":sorted(violations), "simulation_marker_can_authorize_release":False, "inventory_is_not_pass":True, "production_writes":0, "paid_calls":0, "functional_completeness_certified":False}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]); parser.add_argument("--output",type=Path)
    args=parser.parse_args(); result=audit(args.root)
    if args.output: args.output.write_text(json.dumps(result,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True)); raise SystemExit(0 if not result["simulation_marker_can_authorize_release"] else 1)
