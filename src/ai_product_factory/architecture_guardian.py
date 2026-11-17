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
    ("supabase_secret",re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}"),"critical"),
    ("github_token",re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),"critical"),
    ("private_key",re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),"critical"),
)
_SQL_BLOCKERS=(
    ("security_definer",re.compile(r"\bsecurity\s+definer\b",re.I),"error"),
    ("disable_rls",re.compile(r"\bdisable\s+row\s+level\s+security\b",re.I),"critical"),
    # Policy/grant handling is contextual; blanket TO authenticated is wrong.
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



def _bounded_authenticated_invoker_grant(target:str, added:str)->bool:
    """Accept an authenticated EXECUTE grant only with complete RLS evidence.

    A published, explicitly revocable SECURITY INVOKER function runs as the
    authenticated end-user, so the referenced tables' strict RLS is authoritative.
    This *static* classifier is not the PostgreSQL QA or release authorization.
    Missing declaration, signature, revoke, body, tenant policy or FORCE RLS
    denies the grant. In particular SECURITY DEFINER is never accepted here.
    """
    match=re.fullmatch(
        r"function\s+public\.([a-z_][a-z0-9_]*)\s*\(\s*([a-z_,\s]*)\s*\)",
        target,re.I|re.S,
    )
    if match is None:return False
    name=match.group(1).lower()
    signature=",".join(x.strip().lower() for x in match.group(2).split(","))
    if not signature or not all(
        x in {"uuid","text","integer","bigint","boolean","jsonb"}
        for x in signature.split(",")
    ):return False
    clean=re.sub(r"/\*[\s\S]*?\*/|--[^\n]*","",added)
    compact=re.sub(r"\s+","",clean.lower())
    if f"revokeallonfunctionpublic.{name}({signature})frompublic,anon;" not in compact:
        return False
    # Require the exact declaration in the added diff, not a claim in a
    # comment, and not a similarly named function or a different signature.
    decl=re.search(
        r"\bcreate\s+(?:or\s+replace\s+)?function\s+public\."
        +re.escape(name)+r"\s*\(([^)]*)\)\s+returns\s+[a-z_][a-z0-9_]*"
        +r"\s+language\s+plpgsql\s+security\s+invoker"
        +r"\s+set\s+search_path\s*=\s*''\s+as\s+\$([a-z_][a-z0-9_]*)\$",
        clean,re.I|re.S,
    )
    if decl is None:return False
    declared_types=[]
    for arg in decl.group(1).split(","):
        tokens=arg.strip().lower().split()
        if len(tokens)!=2:return False
        declared_types.append(tokens[1])
    if ",".join(declared_types)!=signature:return False
    tag=decl.group(2)
    closing=re.search(r"\$"+re.escape(tag)+r"\$\s*;",clean[decl.end():],re.I)
    if closing is None:return False
    body=clean[decl.end():decl.end()+closing.start()]
    if re.search(
        r"\b(?:execute|security\s+definer|set\s+role|grant|revoke|"
        r"create\s+role|alter\s+role|drop\s+table|truncate)\b",
        body,re.I,
    ):return False
    # Every directly accessed relation must be protected by both ENABLE
    # and FORCE RLS, with an actual end-user/tenant-scoped policy included
    # in this reviewable SQL diff. An invoker cannot silently bypass them.
    tables=set(x.lower() for x in re.findall(
        r"\b(?:from|join|update|into|delete\s+from)\s+public\.([a-z_][a-z0-9_]*)\b",
        body,re.I,
    ))
    if not tables:return False
    statements=[x.strip() for x in clean.split(";")]
    for table in tables:
        for verb in ("enable","force"):
            if not re.search(
                r"\balter\s+table\s+public\."+re.escape(table)
                +r"\s+"+verb+r"\s+row\s+level\s+security\b",
                clean,re.I,
            ):return False
        if not any(
            re.search(r"\bcreate\s+policy\s+[a-z_][a-z0-9_]*\s+on\s+public\."
                      +re.escape(table)+r"\b",stmt,re.I)
            and re.search(r"\bto\s+authenticated\b",stmt,re.I)
            and re.search(r"\bauth\.uid\s*\(",stmt,re.I)
            and re.search(r"\b(?:user_id|owner_id|created_by|actor_id|organization_id)\b",
                          stmt,re.I)
            and re.search(r"\b(?:using|with\s+check)\s*\(",stmt,re.I)
            for stmt in statements
        ):return False
    return True


def _sql_security_findings(path:str,added:str)->list[dict]:
    """Block broad SQL access, allow only reviewable tenant-scoped authenticated RLS.

    This remains a static guard, *not* proof that RLS was executed. PostgreSQL
    QA and release review remain separately mandatory.
    """
    found=[]
    # Distinct complete statements avoid matching role names in unrelated
    # comments or through a later semicolon. Missing statement tail = block.
    statements=[re.sub(r"--[^\n]*","",s).strip()
        for s in added.split(";")[:-1]]
    trailing=added.rsplit(";",1)[-1]
    if re.search(r"\b(?:create\s+policy|grant\s+)\b",trailing,re.I):
        found.append(_finding("unreviewable_sql_permission","error",
            "truncated SQL permission change",path,kind="database_security"))
    for stmt in statements:
        policy=re.search(r"\bcreate\s+policy\b[\s\S]*?\bto\s+(public|anon|authenticated)\b",stmt,re.I)
        if policy:
            role=policy.group(1).lower()
            verb=re.search(r"\bfor\s+(select|insert|update|delete|all)\b",stmt,re.I)
            verb=verb.group(1).lower() if verb else "all"
            has_using=bool(re.search(r"\busing\s*\(",stmt,re.I))
            has_check=bool(re.search(r"\bwith\s+check\s*\(",stmt,re.I))
            # A membership/owner predicate is required; merely being signed in
            # is not a tenant boundary.
            auth=bool(re.search(r"\bauth\.uid\s*\(",stmt,re.I))
            membership=bool(re.search(r"\b(?:from|join)\s+(?:public\.)?[a-z_][a-z0-9_]*",stmt,re.I))
            owner=bool(re.search(r"(?:owner_id|user_id|actor_id|created_by)\s*=\s*\(?\s*(?:select\s+)?auth\.uid\s*\(",stmt,re.I))
            bounded=role=="authenticated" and auth and (membership or owner)
            bounded=bounded and (
                (verb=="insert" and has_check)
                or (verb in ("select","delete") and has_using)
                or (verb=="update" and has_using and has_check)
            ) and not bool(re.search(r"\b(?:using|with\s+check)\s*\(\s*true\s*\)",stmt,re.I))
            if not bounded:
                found.append(_finding("public_rls_policy","error",
                    "unbounded or unreviewable RLS policy",path,kind="database_security"))
        grant=re.search(r"\bgrant\s+(.+?)\s+on\s+(.+?)\s+to\s+(public|anon|authenticated)\s*$",stmt,re.I|re.S)
        if grant:
            rights=grant.group(1).lower()
            if not re.search(r"\b(all|select|insert|update|delete|execute)\b",rights):
                continue
            target=grant.group(2).strip().lower()
            role=grant.group(3).lower()
            safe=False
            if role=="authenticated" and not re.search(r"\ball\b",rights):
                if target=="function auth.uid()":
                    safe=True
                elif target.startswith("function public."):
                    safe=rights.strip()=="execute" and _bounded_authenticated_invoker_grant(target,added)
                else:
                    tables=re.findall(r"\bpublic\.([a-z_][a-z0-9_]*)\b",target,re.I)
                    safe=bool(tables) and "function" not in target
                    for table in tables:
                        if not re.search(
                            r"\balter\s+table\s+public\."+re.escape(table)+r"\s+enable\s+row\s+level\s+security\b",
                            added,re.I,
                        ):
                            safe=False
            if not safe:
                found.append(_finding("permissive_public_grant","error",
                    "unscoped SQL permission grant",path,kind="database_security"))
    return found


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
    unreviewable_paths=[]
    total_files=0

    for row in rows:
        total_files+=1
        if total_files>3000:
            raise RuntimeError("security diff inventory exceeds verified GitHub limit")
        path=str(row.get("filename") or "")
        status=str(row.get("status") or "")
        raw_patch=row.get("patch")
        patch=raw_patch if isinstance(raw_patch,str) else ""
        if not patch.strip():
            # GitHub omits patches for binary/large/unreviewable changes.
            # A scanner cannot attest that code contains no secrets without bytes.
            unreviewable_paths.append(path)
            findings.append(_finding(
                "unreviewable_diff","critical",
                "GitHub did not provide reviewable patch content",path,
                kind="evidence_completeness",
            ))
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
            findings.extend(_sql_security_findings(path,added))
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

    if total_files==0:
        unreviewable_paths.append("<empty PR>")
        findings.append(_finding(
            "empty_diff_inventory","critical",
            "An empty changed-file inventory cannot prove a security review",
            "<empty PR>",kind="evidence_completeness",
        ))

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
        "unreviewable_paths":sorted(set(unreviewable_paths)),
        "files_reviewed":total_files,
        "dependency_surfaces":sorted(set(dependency_surfaces)),
        "api_contracts":api_contracts,
        "database_lineage":sql_lineage,
        "coverage":{
            "diff_content_available":not unreviewable_paths,
            "secret_literals":not unreviewable_paths,
            "client_server_secret_boundary":not unreviewable_paths,
            "workflow_invariants":not unreviewable_paths,
            "sql_rls_rpc_invariants":not unreviewable_paths,
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
                "diff_content_available":not unreviewable_paths,
            }.items() if not value
        ],
    })
