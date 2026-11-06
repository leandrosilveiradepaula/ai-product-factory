"""Fail-closed source audit for privileged Console credential flows.

It reads source only and deliberately records paths/line numbers, never values.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
PRIV=re.compile(r"(?:SUPABASE_SECRET_KEY|SUPABASE_SERVICE_ROLE_KEY|FACTORY_RELEASE_GITHUB_TOKEN|FACTORY_SUPABASE_MANAGEMENT_TOKEN|FACTORY_GITHUB_WORKFLOW_DISPATCH_TOKEN|OPENAI_API_KEY)")
PUBLIC=("apps/console/app/api/health/route.ts",)
def audit(root:Path)->dict:
 root=root.resolve(strict=True); console=root/"apps"/"console"; findings=[]; scanned=0
 for path in sorted(console.rglob("*.ts"))+sorted(console.rglob("*.tsx")):
  if path.is_symlink(): raise ValueError("symlinked_console_source")
  rel=path.relative_to(root).as_posix(); body=path.read_text(encoding="utf-8"); scanned+=1
  public=rel.startswith("apps/console/app/") and ("/api/" in rel or rel.endswith("page.tsx") or rel.endswith("layout.tsx"))
  for n,line in enumerate(body.splitlines(),1):
   if public and PRIV.search(line) and ("process.env" in line or "from \"@/lib/" in line or "from '@/lib/" in line): findings.append({"path":rel,"line":n,"kind":"privileged_source_reaches_public_surface"})
   if "NEXT_PUBLIC_" in line and PRIV.search(line): findings.append({"path":rel,"line":n,"kind":"privileged_next_public_name"})
 return {"schema":"factory-block1-credential-exposure-v1","scope":"source-flow-negative-contract-not-runtime-authentication","console_files_scanned":scanned,"public_exceptions":list(PUBLIC),"findings":findings,"privileged_values_read":False,"credential_exposure_detected":bool(findings),"security_certified":False,"writes":0,"paid_calls":0}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args();r=audit(a.root);print(json.dumps(r,sort_keys=True));raise SystemExit(1 if r["credential_exposure_detected"] else 0)
