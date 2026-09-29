from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GuardianReport:
    findings:tuple[dict,...]
    evidence:dict


_SECRET_PATTERNS=(
    ("openai_key",re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}"),"critical"),
    ("supabase_secret",re.compile(r"\bsb_secret_[A-Za-z0-9_-]{12,}"),"critical"),
    ("github_token",re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),"critical"),
    ("private_key",re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),"critical"),
)
_SQL_BLOCKERS=(
    ("security_definer",re.compile(r"\bsecurity\s+definer\b",re.I),"error"),
    ("disable_rls",re.compile(r"\bdisable\s+row\s+level\s+security\b",re.I),"critical"),
    ("permissive_public_grant",re.compile(r"\bgrant\s+(?:all|select|insert|update|delete|execute).*\bto\s+(?:public|anon|authenticated)\b",re.I),"error"),
    ("public_rls_policy",re.compile(r"\bcreate\s+policy\b[\s\S]{0,300}\bto\s+(?:public|anon|authenticated)\b",re.I),"error"),
)
_WORKFLOW_BLOCKERS=(
    ("pull_request_target",re.compile(r"^\+\s*pull_request_target\s*:",re.I|re.M),"critical"),
    ("write_all_permissions",re.compile(r"^\+\s*permissions\s*:\s*write-all\s*$",re.I|re.M),"critical"),
    ("danger_full_access",re.compile(r"\bdanger-full-access\b"),"critical"),
)
_CLIENT_SECRET_PATTERNS=(
    ("client_service_role",re.compile(r"NEXT_PUBLIC_[A-Z0-9_]*(?:SERVICE_ROLE|SECRET_KEY|PRIVATE_KEY)"),"critical"),
    ("client_openai_key",re.compile(r"NEXT_PUBLIC_[A-Z0-9_]*OPENAI[A-Z0-9_]*KEY"),"critical"),
)

_SQL_OBJECT=re.compile(r"\b(create|alter|drop)\s+(?:or\s+replace\s+)?(table|view|materialized\s+view|function|policy|index)\s+(?:if\s+(?:not\s+)?exists\s+)?(?:public\.)?([A-Za-z_][A-Za-z0-9_]*)",re.I)
_SQL_REFERENCE=re.compile(r"\b(?:from|join|references|update|into)\s+(?:public\.)?([A-Za-z_][A-Za-z0-9_]*)",re.I)


def _added_text(patch:str)->str:
    return "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))


def _finding(code:str,severity:str,message:str,path:str,*,scope_keys:Iterable[str]|None=None,kind:str="architecture")->dict:
    return {
        "code":code,"severity":severity,"message":message,"path":path,
        "scope_keys":list(scope_keys or (path,)),"kind":kind,"source":"architecture_guardian_v1",
    }


def _sql_lineage(path:str,text:str)->dict:
    objects=[]
    references=[]
    for action,kind,name in _SQL_OBJECT.findall(text):
        row={"action":action.lower(),"kind":" ".join(kind.lower().split()),"name":name}
        if row not in objects:objects.append(row)
    for name in _SQL_REFERENCE.findall(text):
        if name not in references:references.append(name)
    return {"path":path,"objects":objects,"references":sorted(references)}


def _api_contract_fact(path:str,status:str)->dict|None:
    normalized=path.replace("\\","/")
    if "/app/api/" in normalized and normalized.endswith(("/route.ts","/route.js")):
        return {"path":path,"status":status,"kind":"next_route","requires_contract_evidence":True}
    if normalized.startswith(("api/","src/api/")):
        return {"path":path,"status":status,"kind":"api_surface","requires_contract_evidence":True}
    return None


def scan_pull_request_files(rows:Iterable[dict])->GuardianReport:
    findings=[]
    sensitive_paths=set()
    dependency_surfaces=[]
    api_contracts=[]
    sql_lineage=[]
    workflow_paths=[]

    for row in rows:
        path=str(row.get("filename") or "")
        status=str(row.get("status") or "")
        patch=str(row.get("patch") or "")
        added=_added_text(patch)
        lower=path.lower()

        for code,pattern,severity in _SECRET_PATTERNS:
            if pattern.search(added):
                findings.append(_finding(code,severity,f"secret-like literal added: {code}",path,kind="secret_scan"))

        if path.startswith("apps/console/") or "/app/" in path:
            for code,pattern,severity in _CLIENT_SECRET_PATTERNS:
                if pattern.search(added):
                    findings.append(_finding(code,severity,f"client/server secret boundary violated: {code}",path,kind="client_boundary"))

        if path.startswith(".github/workflows/") or path.startswith(".github/actions/"):
            workflow_paths.append(path)
            for code,pattern,severity in _WORKFLOW_BLOCKERS:
                if pattern.search(patch):
                    findings.append(_finding(code,severity,f"unsafe GitHub workflow invariant matched: {code}",path,kind="workflow_security"))

        if path.startswith("supabase/migrations/") or lower.endswith(".sql"):
            sql_lineage.append(_sql_lineage(path,added))
            for code,pattern,severity in _SQL_BLOCKERS:
                if pattern.search(added):
                    findings.append(_finding(code,severity,f"database security invariant matched: {code}",path,kind="database_security"))
            if re.search(r"\bdrop\s+(?:table|column|view|function)\b",added,re.I):
                findings.append(_finding(
                    "destructive_schema_change","warning",
                    "destructive schema operation requires explicit impact/rollback evidence",path,kind="database_lineage",
                ))

        if path.endswith(("package.json","package-lock.json","pnpm-lock.yaml","yarn.lock","requirements.txt","poetry.lock","pyproject.toml")):
            dependency_surfaces.append(path)

        fact=_api_contract_fact(path,status)
        if fact:api_contracts.append(fact)

        if any(part in lower for part in ("auth","security","supabase/migrations",".github/workflows","vercel.json","package.json","lock")):
            sensitive_paths.add(path)

    if dependency_surfaces:
        findings.append(_finding(
            "dependency_surface_changed","warning",
            "dependency manifest/lockfile changed; deterministic dependency audit/SBOM evidence is required before release",
            dependency_surfaces[0],scope_keys=dependency_surfaces,kind="dependency_surface",
        ))
    if api_contracts:
        findings.append(_finding(
            "api_contract_surface_changed","warning",
            "API surface changed; contract/consumer compatibility evidence is required",
            api_contracts[0]["path"],scope_keys=[x["path"] for x in api_contracts],kind="api_contract",
        ))

    blocking=tuple(x for x in findings if x["severity"] in {"critical","error"})
    return GuardianReport(tuple(findings),{
        "scanner":"architecture_guardian_v1",
        "model_call":False,
        "blocking_findings":len(blocking),
        "sensitive_paths":sorted(sensitive_paths),
        "workflow_paths":sorted(set(workflow_paths)),
        "dependency_surfaces":sorted(set(dependency_surfaces)),
        "api_contracts":api_contracts,
        "database_lineage":sql_lineage,
        "coverage":{
            "secret_literals":True,
            "client_server_secret_boundary":True,
            "workflow_invariants":True,
            "sql_rls_rpc_invariants":True,
            "dependency_vulnerability_scan":False,
            "sbom_generation":False,
            "full_sast":False,
            "api_semantic_compatibility":False,
        },
        "unknowns":[
            key for key,value in {
                "dependency_vulnerability_scan":False,
                "sbom_generation":False,
                "full_sast":False,
                "api_semantic_compatibility":False,
            }.items() if not value
        ],
    })
