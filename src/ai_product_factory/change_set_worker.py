from __future__ import annotations

from dataclasses import dataclass,replace
import hashlib
import re
from typing import Protocol

from .change_set_store import ChangeSetBinding,SupabaseChangeSetStore
from .execution_worker import DirectExecutionItem,ImplementationArtifact,ImplementationProducer,ImplementationBlocked
from .github_rest import GitHubRestAdapter
from .impact_engine import SupabaseImpactEngine
from .work_unit_context import build_context_packet,enforce_write_scopes,redact_repository_text
from .provenance_replay import SupabaseProvenanceStore,build_run_provenance
from .commit_provenance import provenance_commit_message
from .pinned_nonproduction_target import PinnedNonproductionTarget


@dataclass(frozen=True)
class ChangeSetWorkResult:
    run_id:str
    change_set_id:str
    work_unit_id:str
    output_commit:str
    changed_files:tuple[str,...]
    base_commit:str
    branch:str


class ChangeSetBuilderWorker:
    _DISCOVERY_STOP={"application","implementation","remediation","coverage","regression","route","task","change","update","fix","feature","work"}
    _TEXT_EXTENSIONS=(".py",".ts",".tsx",".js",".jsx",".mjs",".cjs",".json",".sql",".md",".yaml",".yml",".toml")

    # No arbitrary root write scope is granted to an empty repository. Only
    # these structural locations can be created for the FIRST foundation wave,
    # and only when every requested scope has an explicit deterministic map.
    # No .github/, live .env, credentials, deployment or production paths.
    _GREENFIELD_EXISTING={"README.md","LICENSE","LICENSE.md",".gitignore","AGENTS.md","docs/codex/CURRENT_TASK.md"}
    _GREENFIELD_SCOPES={
        "application-foundation":(
            "package.json","package-lock.json","tsconfig.json",".gitignore",
            "src/**","app/**","tests/**","test/**",
        ),
        "database-migrations":("supabase/migrations/**","db/migrations/**","migrations/**"),
        "environment-template":("src/config/**","config/**"),
        "domain-shared":("src/domain/**","src/shared/**","src/lib/**"),
    }

    @classmethod
    def _greenfield_scopes(cls,*,source:dict,all_paths:tuple[str,...],
                           assignment:dict)->tuple[str,...]|None:
        """Recognize only an empty-code first foundation wave from the plan.

        The original README is mandatory context; neither the model nor a
        semantic scope can invent broad repository access. Populated repos,
        arbitrary task keys, unrecognized scopes, and later waves remain
        subject to the strict repository-context discovery path.
        """
        if source.get("wave") != 1 or "README.md" not in all_paths:
            return None
        if not set(all_paths).issubset(cls._GREENFIELD_EXISTING):
            return None
        task_key=cls._tokens(source.get("plan_task_key"))
        if not (task_key & {"foundation","bootstrap","scaffold"}):
            return None
        requested=assignment.get("scope_keys")
        if not isinstance(requested,list) or not requested:
            return None
        if any(not isinstance(scope,str) or scope not in cls._GREENFIELD_SCOPES
               for scope in requested):
            return None
        if "application-foundation" not in requested:
            return None
        return tuple(dict.fromkeys(
            safe_path
            for key in requested
            for safe_path in cls._GREENFIELD_SCOPES[key]
        ))


    # These are structural namespaces, not unrestricted filesystem prefixes.
    # Project kind comes from the privileged Control Plane project record, not
    # a model answer or repository README. Unknown semantic keys remain blocked.
    _GREENFIELD_CONTINUATION_ROOTS={
        "auth":("src/auth","src/security/auth","src/interface/auth","src/integrations/identity-provider",
                "tests/auth","tests/session"),
        "authorization":("src/authorization","src/security/authorization","src/security/rbac",
                         "src/security/permissions","src/application/authorization",
                         "tests/authorization","tests/rbac"),
        "frontend-app":("app","src/app","src/ui","src/components","src/styles","tests/ui"),
        "design-system":("src/components/ui","src/styles","src/theme","app/globals.css",
                         "src/app/globals.css","tests/ui/design"),
        "navigation":("src/navigation","src/components/navigation","app/layout.tsx",
                      "src/app/layout.tsx","tests/ui/navigation"),
        "search":("src/search","src/application/search","tests/search"),
        "search-and-filters":("src/application/search","src/application/filters",
                              "src/interface/search","tests/search","tests/filters"),
        "openapi":("docs/openapi","openapi.yaml","openapi.json","src/interface/openapi",
                   "tests/openapi"),
        "webhooks":("src/integrations/webhooks","src/interface/webhooks",
                    "app/api/webhooks","tests/webhooks"),
        "outbox":("src/integrations/outbox","src/domain/outbox",
                  "src/application/outbox","tests/outbox"),
        "notifications":("src/notifications","src/application/notifications",
                         "tests/notifications"),
        "dashboards":("src/ui/dashboards","src/components/dashboard","app/dashboard",
                      "tests/ui/dashboards"),
        "exports":("src/export","src/application/exports","tests/exports"),
        "queues":("src/domain/queues","src/ui/queues","tests/queues"),
        "saved-views":("src/domain/saved-views","src/ui/saved-views","tests/saved-views"),
        "time-tracking":("src/domain/time-tracking","src/application/time-tracking",
                         "tests/time-tracking"),
        "data-lifecycle":("src/domain/data-lifecycle","src/application/data-lifecycle",
                          "tests/data-lifecycle"),
        "analytics-queries":("src/analytics","src/reporting/queries","tests/analytics"),
    }
    _GREENFIELD_CONTINUATION_MIGRATIONS=("supabase/migrations","db/migrations","migrations")

    @staticmethod
    def _structural_scopes(*roots:str)->tuple[str,...]:
        result=[]
        for root in roots:
            if root.endswith((".ts",".tsx",".py",".sql",".json",".yaml",".yml",".css")):
                result.append(root)
            else:
                result.extend((f"{root}/**",f"{root}.ts",f"{root}.tsx",f"{root}.py"))
        return tuple(dict.fromkeys(result))

    @classmethod
    def _continuation_semantic_scopes(cls,scope:str,all_paths:tuple[str,...])->tuple[str,...]|None:
        """Map a declared semantic scope only to its bounded architectural namespace.

        Supports future product domains without granting src/**, repo root,
        .github/**, credentials, arbitrary deployment files, or unrecognized keys.
        Migration writes require evidence that a versioned migration root exists.
        """
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*",scope) or len(scope)>64:
            return None
        migration_root=next((
            root for root in cls._GREENFIELD_CONTINUATION_MIGRATIONS
            if any(path.startswith(root+"/") for path in all_paths)
        ),None)
        if scope=="database-migrations":
            return (migration_root+"/**",) if migration_root else None
        if scope in ("rls-policies","storage-policies"):
            if not migration_root:
                return None
            roots=("tests/rls","tests/tenant-isolation") if scope=="rls-policies" else (
                "src/storage/policies","tests/storage",
            )
            return (migration_root+"/**",*cls._structural_scopes(*roots),
                    "tests/tenant-isolation.test.ts" if scope=="rls-policies"
                    else "tests/storage-policies.test.ts")
        if scope in cls._GREENFIELD_CONTINUATION_ROOTS:
            return cls._structural_scopes(*cls._GREENFIELD_CONTINUATION_ROOTS[scope])
        for suffix,roots in (
            ("-domain",("src/domain","src/application","src/persistence","tests")),
            ("-ui",("src/ui","src/components","app","tests/ui")),
            ("-api",("src/interface/api","src/api","app/api","tests/api")),
            ("-services",("src/services","src/application","tests")),
            ("-jobs",("src/jobs","src/automation","tests/jobs")),
            ("-workspace",("src/ui","src/components","app","tests/ui")),
            ("-portal",("src/ui","src/components","app","tests/ui")),
            ("-layouts",("src/layouts","src/components/layouts","tests/ui")),
            ("-queries",("src/analytics","src/reporting","tests/analytics")),
        ):
            if scope.endswith(suffix):
                stem=scope[:-len(suffix)]
                if not stem:
                    return None
                branches=[f"{root}/{stem}" for root in roots]
                if scope=="tenant-domain":
                    branches.extend((
                        "src/domain/tenancy","src/application/tenancy",
                        "src/persistence/tenancy","tests/tenancy",
                    ))
                return cls._structural_scopes(*branches)
        return None

    @staticmethod
    def _has_greenfield_foundation(all_paths:tuple[str,...])->bool:
        return (
            "README.md" in all_paths
            and ("package.json" in all_paths or "pyproject.toml" in all_paths)
            and any(path.startswith("src/") for path in all_paths)
        )

    def __init__(self,*,github:GitHubRestAdapter,store:SupabaseChangeSetStore,producer:ImplementationProducer,
                 impact_engine:SupabaseImpactEngine|None=None,provenance:SupabaseProvenanceStore|None=None,
                 execution_route:str="direct")->None:
        self.github=github;self.store=store;self.producer=producer;self.impact_engine=impact_engine or SupabaseImpactEngine()
        self.provenance=provenance or SupabaseProvenanceStore();self.execution_route=execution_route

    @classmethod
    def _tokens(cls,value:object)->set[str]:
        parts=re.findall(r"[a-z0-9]+",str(value or "").lower())
        return {part for part in parts if len(part)>=3 and part not in cls._DISCOVERY_STOP}

    @staticmethod
    def _normalize_path(value:object)->str:
        return str(value or "").strip().replace("\\","/").removeprefix("./").strip("/")

    @classmethod
    def _is_test_scope(cls,value:str)->bool:
        tokens=cls._tokens(value)
        return bool(tokens & {"test","tests","teste","testes","testing","spec","specs","regression"})

    @classmethod
    def _bounded_file_scope(cls, raw:str, all_paths:tuple[str,...])->tuple[str,str|None]|None:
        """Recognize an exact file plus optional conditional prose, never a prose path.

        A new file is allowed only in an already populated code directory. Neither
        a broad namespace nor a guessed SQL/migration/credential file is created.
        """
        match=re.fullmatch(
            r"(?P<path>(?:src|app|apps|packages|test|tests|docs)/[A-Za-z0-9_./()\-]+\.(?:tsx?|jsx?|py|md))"
            r"(?:\s+(?P<condition>(?:somente\s+se|se\s+necess[aá]rio|only\s+if|if\s+needed)\b.*))?",
            raw,flags=re.IGNORECASE,
        )
        if not match:
            return None
        path=match.group("path")
        segments=path.split("/")
        if (len(segments)<3 or any(segment in ("",".","..") or segment.startswith(".") for segment in segments)
                or "//" in path or "/.github/" in path.lower()):
            return None
        if path not in all_paths:
            if (not path.startswith(("src/","app/","apps/","packages/","test/","tests/"))
                    or not path.endswith((".py",".ts",".tsx",".js",".jsx"))):
                return None
            parent=path.rsplit("/",1)[0]+"/"
            if not any(existing.startswith(parent) for existing in all_paths):
                return None
        return path,match.group("condition")

    @classmethod
    def _co_located_test_scopes(cls, paths:list[str], all_paths:tuple[str,...])->tuple[str,...]:
        """Bound test authorization to exact siblings of declared source files."""
        tests=[]
        for path in paths:
            if (not path.startswith(("src/","app/","apps/","packages/"))
                    or not path.endswith((".py",".ts",".tsx",".js",".jsx"))
                    or re.search(r"\.(?:test|spec)\.",path,re.IGNORECASE)):
                continue
            stem,ext=path.rsplit(".",1)
            candidates=[f"{stem}.test.{ext}",f"{stem}.spec.{ext}"]
            if ext=="py" and any(p.startswith("tests/") for p in all_paths):
                candidates.insert(0,"tests/test_"+stem.rsplit("/",1)[-1]+".py")
            existing=next((p for p in candidates if p in all_paths),None)
            target=existing or candidates[0]
            if target not in tests:
                tests.append(target)
            if len(tests)==3:
                break
        return tuple(tests)

    @classmethod
    def _governance_paths(cls,paths:tuple[str,...])->tuple[str,...]:
        preferred=("AGENTS.md","docs/codex/CURRENT_TASK.md")
        return tuple(path for path in preferred if path in paths)

    @classmethod
    def _score_path(cls,path:str,tokens:set[str])->int:
        lower=path.lower()
        score=0
        for token in tokens:
            if token in lower:
                score+=3 if f"/{token}/" in f"/{lower}/" else 1
        if score<=0:
            return 0
        if lower.endswith((".ts",".tsx",".js",".jsx",".py")):
            score+=1
        if lower.startswith(("docs/","documentation/")):
            score=max(1,score-1)
        return score

    def _resolved_repository_context(self,*,source:dict,base_commit:str)->tuple[dict,tuple[str,...]]:
        assignment=dict(source.get("assignment") if isinstance(source.get("assignment"),dict) else {})
        explicit=assignment.get("context_paths") if isinstance(assignment.get("context_paths"),list) else []
        all_paths=self.github.list_file_paths(ref=base_commit)
        governance=self._governance_paths(all_paths)
        continuation=(
            source.get("project_kind")=="greenfield"
            and isinstance(source.get("wave"),int)
            and source["wave"]>=2
        )
        if continuation and not self._has_greenfield_foundation(all_paths):
            raise RuntimeError("greenfield continuation requires an existing, verified foundation")

        # Greenfield bootstrap: the README is the only existing source, so
        # keyword-ranked repository context would otherwise be empty. Require
        # the explicit foundation task + first wave + fully-known semantic
        # scope map before permitting narrowly bounded file creation.
        if not explicit:
            scaffold_scopes=self._greenfield_scopes(
                source=source,all_paths=all_paths,assignment=assignment,
            )
            if scaffold_scopes:
                context_paths=list(dict.fromkeys([*governance,"README.md"]))
                assignment["context_paths"]=context_paths
                assignment["scope_keys"]=list(scaffold_scopes)
                enriched=dict(source)
                enriched["assignment"]=assignment
                return enriched,tuple(context_paths)

        if explicit:
            context_paths=[self._normalize_path(path) for path in explicit]
        else:
            task=source.get("task") if isinstance(source.get("task"),dict) else {}
            raw_scopes=assignment.get("scope_keys") if isinstance(assignment.get("scope_keys"),list) else []
            tokens=set()
            for value in (
                source.get("plan_task_key"),task.get("title"),task.get("description"),
                " ".join(str(x) for x in (task.get("acceptance_criteria") or [])),
                " ".join(str(x) for x in raw_scopes),
            ):
                tokens.update(self._tokens(value))
            ranked=[
                (self._score_path(path,tokens),path)
                for path in all_paths
                if path.endswith(self._TEXT_EXTENSIONS) and path not in governance
            ]
            ranked=[row for row in ranked if row[0]>0]
            ranked.sort(key=lambda row:(-row[0],len(row[1]),row[1]))
            context_paths=[path for _,path in ranked[:8]]
            if not context_paths and continuation:
                # A new bounded feature may have no same-named files yet. Read
                # existing foundational code, not fabricated paths or metadata.
                context_paths=[
                    path for path in ("package.json","pyproject.toml","tsconfig.json","README.md")
                    if path in all_paths
                ]
                context_paths.extend(sorted(path for path in all_paths
                    if path.startswith("src/") and path.endswith(self._TEXT_EXTENSIONS))[:3])
            if not context_paths:
                raise RuntimeError("repository context discovery found no relevant files; replan with explicit context_paths")

        raw_scopes=assignment.get("scope_keys") if isinstance(assignment.get("scope_keys"),list) else []
        normalized_scopes=[]
        precise_scopes=[]
        conditional_notes=[]
        for raw in raw_scopes:
            literal=str(raw or "").strip().replace("\\","/")
            if literal.startswith("/") or literal.startswith("../") or ".." in literal.split("/"):
                raise PermissionError("planned write scope contains an unsafe path")
            scope=self._normalize_path(raw)
            if not scope:
                continue
            exact=self._bounded_file_scope(scope,all_paths)
            if exact:
                scope,condition=exact
                precise_scopes.append(scope)
                if condition:
                    conditional_notes.append(
                        f"Conditional write: {scope} only if the task's stated condition "
                        f"is confirmed in the pinned repository evidence: {condition}"
                    )
            normalized_scopes.append(scope)
        exact_scope_context=[
            scope for scope in normalized_scopes
            if scope in all_paths and scope.endswith(self._TEXT_EXTENSIONS)
        ]

        required_context=list(dict.fromkeys([*governance,*exact_scope_context]))
        optional_context=[path for path in context_paths if path not in required_context]
        if len(required_context)>12:
            raise ValueError("too many required repository context paths")
        context_paths=[*required_context,*optional_context[:12-len(required_context)]]

        resolved_scopes=[]
        semantic_scopes=[]
        for scope in normalized_scopes:
            prefix=scope[:-3].rstrip("/") if scope.endswith("/**") else scope.rstrip("/")
            if continuation and scope==".":
                raise PermissionError("greenfield continuation cannot use repository-root write scope")
            if scope=="." or any(path==prefix or path.startswith(prefix+"/") for path in all_paths):
                resolved_scopes.append(scope)
            elif scope in precise_scopes:
                # The exact new file has a verified existing parent; never
                # substitute a different path merely because keywords match.
                resolved_scopes.append(scope)
            elif continuation:
                mapped=self._continuation_semantic_scopes(scope,all_paths)
                if not mapped:
                    raise RuntimeError(f"greenfield semantic scope is not safely mapped: {scope}")
                resolved_scopes.extend(mapped)
            else:
                semantic_scopes.append(scope)

        editable_context=[path for path in context_paths if path not in governance]
        for semantic in semantic_scopes:
            if self._is_test_scope(semantic):
                if any(ch.isspace() for ch in semantic) or self._tokens(semantic) & {"teste","testes"}:
                    # Natural-language test scopes must never become tests/**
                    # or arbitrary tests unrelated to the authorized code.
                    related=self._co_located_test_scopes(precise_scopes,all_paths)
                    if not related:
                        raise RuntimeError(
                            "descriptive test scope requires an exact related code file"
                        )
                    resolved_scopes.extend(related)
                    continue
                semantic_tokens=self._tokens(semantic)-{"test","tests","testing","spec","specs","regression"}
                test_matches=[
                    path for path in all_paths
                    if ("test" in path.lower() or "spec" in path.lower())
                    and (not semantic_tokens or any(token in path.lower() for token in semantic_tokens))
                    and path.endswith(self._TEXT_EXTENSIONS)
                ]
                if test_matches:
                    resolved_scopes.extend(test_matches[:6])
                else:
                    conventional=next((root for root in ("test","tests") if any(path.startswith(root+"/") for path in all_paths)),None)
                    if conventional:
                        resolved_scopes.append(conventional+"/**")
                    else:
                        raise RuntimeError(f"semantic test scope could not be resolved safely: {semantic}")
            else:
                if any(ch.isspace() for ch in semantic):
                    raise RuntimeError("descriptive write scope requires an exact repository path")
                semantic_tokens=self._tokens(semantic)
                matches=[
                    path for path in editable_context
                    if not semantic_tokens or any(token in path.lower() for token in semantic_tokens)
                ]
                if not matches:
                    matches=editable_context[:1] if len(editable_context)==1 else []
                if not matches:
                    raise RuntimeError(f"semantic write scope could not be resolved safely: {semantic}")
                resolved_scopes.extend(matches)

        resolved_scopes=list(dict.fromkeys(resolved_scopes))
        if not resolved_scopes:
            raise PermissionError("work unit has no safely resolved write scopes")

        assignment["scope_keys"]=resolved_scopes
        assignment["context_paths"]=context_paths
        enriched=dict(source)
        enriched["assignment"]=assignment
        if conditional_notes:
            previous=enriched.get("constraints")
            enriched["constraints"]=[
                *(previous if isinstance(previous,list) else []),
                *conditional_notes,
            ]
        return enriched,tuple(context_paths)

    _MAX_SNAPSHOT_BYTES = 131072
    _MAX_OPTIONAL_CONTEXT_BYTES = 16384

    def _repository_snapshot_with_safety(
        self, *, source: dict, base_commit: str
    ) -> tuple[dict[str, str], frozenset[str]]:
        """Read the exact-SHA sources without exposing incomplete files as editable.

        Governance and explicitly named write targets must be complete. Other
        context is budgeted deterministically, with a read-only excerpt marker.
        Truncated or redacted files are never eligible for an output commit,
        even when a broader assigned write scope would otherwise allow them.
        """
        assignment = source.get("assignment") if isinstance(source.get("assignment"), dict) else {}
        requested = assignment.get("context_paths") if isinstance(assignment.get("context_paths"), list) else []
        scopes = assignment.get("scope_keys") if isinstance(assignment.get("scope_keys"), list) else []
        if len(requested) > 12:
            raise ValueError("too many repository context paths")
        paths = []
        for raw in requested:
            path = str(raw).strip().replace("\\", "/").removeprefix("./")
            if not path or path.startswith("/") or any(
                part in ("", ".", "..", ".git") for part in path.split("/")
            ):
                raise ValueError("invalid repository context path")
            if path not in paths:
                paths.append(path)
        exact_scopes = {
            str(raw).strip().replace("\\", "/").removeprefix("./")
            for raw in scopes if isinstance(raw, str)
        }
        governance = set(self._governance_paths(tuple(paths)))
        required = governance | (set(paths) & exact_scopes)
        ordered = [path for path in paths if path in required] + [
            path for path in paths if path not in required
        ]
        snapshot: dict[str, str] = {}
        unsafe: set[str] = set()
        used_bytes = 0
        optional_left = len(ordered) - len(required)
        for path in ordered:
            try:
                original = self.github.get_file_text(path, ref=base_commit)
            except ValueError as exc:
                if "repository context file too large" in str(exc):
                    # Record the exact path and whether omission is allowed.
                    # Never include file content or secrets in the error.
                    if path in required:
                        raise ValueError(
                            "required repository context file too large: " + path
                        ) from exc
                # Optional context may be rejected by the provider before
                # the bounded excerpt logic runs. Required context stays
                # fail-closed, including governance and exact write targets.
                if path in required or "repository context file too large" not in str(exc):
                    raise
                unsafe.add(path)
                optional_left -= 1
                continue
            clean = redact_repository_text(original)
            encoded = clean.encode("utf-8")
            if clean != original:
                unsafe.add(path)
                if path in exact_scopes:
                    raise PermissionError(
                        "editable repository context contains redacted secret: " + path
                    )
            if path in required:
                if used_bytes + len(encoded) > self._MAX_SNAPSHOT_BYTES:
                    raise ValueError(
                        "complete required repository context exceeds safe budget; "
                        "replan with narrower exact write scopes"
                    )
                value = clean
            else:
                available = self._MAX_SNAPSHOT_BYTES - used_bytes
                allowance = min(
                    self._MAX_OPTIONAL_CONTEXT_BYTES,
                    available // optional_left if optional_left else 0,
                )
                optional_left -= 1
                if len(encoded) <= allowance:
                    value = clean
                else:
                    unsafe.add(path)
                    digest = hashlib.sha256(encoded).hexdigest()
                    marker = (
                        "\n[CONTEXT_EXCERPT path=" + path
                        + " sha256=" + digest + " original_bytes=" + str(len(encoded))
                        + "; INCOMPLETE READ-ONLY CONTEXT; full-file edits forbidden]\n"
                    )
                    marker_size = len(marker.encode("utf-8"))
                    if allowance <= marker_size:
                        # Context can be omitted, but must never exceed its
                        # shared budget or silently become writable.
                        continue
                    head_size = (allowance - marker_size) // 2
                    tail_size = allowance - marker_size - head_size
                    prefix = encoded[:head_size].decode("utf-8", errors="ignore")
                    suffix = encoded[-tail_size:].decode("utf-8", errors="ignore")
                    value = prefix + marker + suffix
            size = len(value.encode("utf-8"))
            if used_bytes + size > self._MAX_SNAPSHOT_BYTES:
                raise RuntimeError("repository context accounting exceeded safe budget")
            snapshot[path] = value
            used_bytes += size
        return snapshot, frozenset(unsafe)

    def _repository_snapshot(self, *, source: dict, base_commit: str) -> dict[str, str]:
        """Backward-compatible snapshot reader; execution uses the safety receipt."""
        return self._repository_snapshot_with_safety(
            source=source, base_commit=base_commit
        )[0]

    @staticmethod
    def _assert_snapshot_edit_safety(
        files: dict[str, str], unsafe_paths: frozenset[str]
    ) -> None:
        forbidden = sorted(set(files) & unsafe_paths)
        if forbidden:
            raise PermissionError(
                "implementation attempted to rewrite incomplete or redacted "
                "repository context: " + ", ".join(forbidden)
            )

    def execute(self,item:DirectExecutionItem)->ChangeSetWorkResult:
        if item.human_gate_required:
            raise PermissionError("task requires human approval before implementation")
        if not item.change_set_id or not item.work_unit_id:
            raise ValueError("Change Set identity is required")
        integration_branch=f"factory/change-set-{item.change_set_id[:8]}"
        try:
            source=self.store.context_source(item.run_id)
            if source.get("project_key") != item.project_key or source.get("repository") != item.repository:
                raise PermissionError("work unit project/repository differs from claimed run")
            if source.get("project_kind")=="existing":
                target=PinnedNonproductionTarget.parse(source.get("delivery_target"),repository=item.repository)
                target.verify(self.github)
                verified_source=target.sha
            elif source.get("project_kind") in (None,"","greenfield"):
                verified_source=self.github.get_branch_sha("main")
            else:
                raise PermissionError("unrecognized project kind")
            frozen_source=self.store.frozen_source_commit(item.change_set_id)
            if source.get("project_kind")=="existing" and frozen_source and frozen_source != verified_source:
                raise PermissionError("frozen Change Set source differs from pinned candidate")
            source_commit=frozen_source or verified_source
            binding=self.store.bind_source(
                run_id=item.run_id,source_commit=source_commit,
                integration_branch=integration_branch,work_branch=item.branch,
            )
            self.github.ensure_branch_at_sha(item.branch,binding.base_commit)
            impact=self.impact_engine.analyze_run(
                project_key=item.project_key,task_id=item.task_id,run_id=item.run_id,change_set_id=item.change_set_id
            )
            source=self.store.context_source(item.run_id)
            source,_=self._resolved_repository_context(source=source,base_commit=binding.base_commit)
            snapshot,unsafe_context_paths=self._repository_snapshot_with_safety(
                source=source,base_commit=binding.base_commit,
            )
            if not snapshot:
                raise RuntimeError("repository context preflight produced an empty snapshot")
            if unsafe_context_paths:
                source=dict(source)
                source["constraints"]=[
                    *(source.get("constraints") if isinstance(source.get("constraints"),list) else []),
                    "Repository context excerpts and redacted files are read-only; "
                    "rewriting these paths will be rejected before commit.",
                ]
            packet=build_context_packet(
                source=source,impact=impact.as_context(),base_commit=binding.base_commit,branch=item.branch,
                repository_snapshot=snapshot,
            )
            self.store.record_context(run_id=item.run_id,packet_hash=packet.sha256,packet=packet.as_dict())
            provenance=build_run_provenance(
                run_id=item.run_id,project_key=item.project_key,route=self.execution_route,
                agent_key=str(source.get("agent_key") or "") or None,context_packet=packet.as_dict(),
                team_plan={"version":source.get("team_plan_version")} if source.get("team_plan_version") is not None else None,
                project_manifest=source.get("project_manifest") if isinstance(source.get("project_manifest"),dict) else {},
                candidate_commit=binding.base_commit,
            )
            self.provenance.record(run_id=item.run_id,snapshot=provenance)
            write_scopes=tuple(packet.payload["repository"]["write_scopes"])
            item=replace(
                item,impact_context=impact.as_context(),base_commit=binding.base_commit,
                context_packet=packet.as_dict(),write_scopes=write_scopes,
            )
            self.store.set_repair_status(run_id=item.run_id,status="running")
        except Exception as exc:
            self.store.block_work_unit(
                run_id=item.run_id,
                reason=f"{type(exc).__name__}: {str(exc)}",
                blocker_type="implementation_preflight_error",
            )
            raise
        try:
            artifact=self.producer.produce(item)
        except Exception as exc:
            self.store.block_work_unit(
                run_id=item.run_id,
                reason=f"{type(exc).__name__}: {str(exc)}",
                blocker_type="implementation_producer_error",
            )
            raise
        if artifact.blocked_reason:
            self.store.block_work_unit(
                run_id=item.run_id,
                reason=artifact.blocked_reason,
                blocker_type="repository_governance",
            )
            raise ImplementationBlocked(artifact.blocked_reason)
        if not artifact.files:
            self.store.block_work_unit(
                run_id=item.run_id,
                reason="implementation producer returned no files",
                blocker_type="implementation_producer_error",
            )
            raise ValueError("implementation producer returned no files")
        try:
            self._assert_snapshot_edit_safety(artifact.files,unsafe_context_paths)
            enforce_write_scopes(artifact.files.keys(),write_scopes)
        except (PermissionError, ValueError) as exc:
            # A model-produced patch outside the approved frozen-plan scopes
            # must never be committed or left silently leased/running.
            self.store.block_work_unit(
                run_id=item.run_id,
                reason=f"{type(exc).__name__}: {str(exc)}",
                blocker_type="repository_governance",
            )
            raise
        commit_message=provenance_commit_message(artifact.commit_message,{
            "Factory-Run":item.run_id,
            "Factory-Change-Set":binding.change_set_id,
            "Factory-Work-Unit":binding.work_unit_id,
            "Factory-Agent":str(source.get("agent_key") or "unknown"),
            "Factory-Context-SHA256":packet.sha256,
        })
        output=self.github.commit_files(item.branch,artifact.files,message=commit_message)
        self.store.complete_work_unit(
            run_id=item.run_id,output_commit=output,changed_files=tuple(sorted(artifact.files)),
        )
        return ChangeSetWorkResult(
            run_id=item.run_id,change_set_id=binding.change_set_id,work_unit_id=binding.work_unit_id,
            output_commit=output,changed_files=tuple(sorted(artifact.files)),base_commit=binding.base_commit,branch=item.branch,
        )
