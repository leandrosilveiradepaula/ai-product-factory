from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from .execution_worker import DirectExecutionItem, ImplementationArtifact
from .github_auth import resolve_github_token


Runner=Callable[[tuple[str,...],Path,dict[str,str],float],tuple[int,str,str]]


def _default_runner(argv:tuple[str,...],cwd:Path,env:dict[str,str],timeout:float)->tuple[int,str,str]:
    completed=subprocess.run(list(argv),cwd=str(cwd),env=env,capture_output=True,text=True,timeout=timeout,check=False)
    return completed.returncode,completed.stdout,completed.stderr


@dataclass(frozen=True)
class CodexCliConfig:
    executable:str="codex"
    timeout_seconds:float=900.0
    max_files:int=40
    max_total_bytes:int=2_000_000

    def validate(self)->None:
        if not self.executable.strip(): raise ValueError("Codex executable is required")
        if self.timeout_seconds<=0: raise ValueError("Codex timeout must be positive")
        if self.max_files<1: raise ValueError("Codex max_files must be positive")
        if self.max_total_bytes<1: raise ValueError("Codex max_total_bytes must be positive")


class CodexCliImplementationProducer:
    """Runs Codex in an isolated checkout and returns a bounded text patch."""

    def __init__(self,config:CodexCliConfig|None=None,*,runner:Runner|None=None)->None:
        self.config=config or CodexCliConfig()
        self.config.validate()
        self.runner=runner or _default_runner
        self.last_trace_events=0

    @staticmethod
    def _safe_codex_env()->dict[str,str]:
        blocked_exact={
            "FACTORY_GITHUB_TOKEN","GITHUB_TOKEN","OPENAI_API_KEY","CODEX_API_KEY","CODEX_ACCESS_TOKEN",
            "SUPABASE_SECRET_KEY","SUPABASE_SERVICE_ROLE_KEY","VERCEL_TOKEN",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN","ACTIONS_ID_TOKEN_REQUEST_URL",
        }
        blocked_prefixes=("AWS_","AZURE_","GOOGLE_","GCP_")
        env={}
        for key,value in os.environ.items():
            if key in blocked_exact or any(key.startswith(prefix) for prefix in blocked_prefixes):
                continue
            env[key]=value
        return env

    @staticmethod
    def _validate_path(path:str)->PurePosixPath:
        p=PurePosixPath(path)
        if p.is_absolute() or ".." in p.parts or not p.parts:
            raise ValueError(f"unsafe Codex path: {path}")
        lower=path.lower()
        name=p.name.lower()
        if p.parts[0]==".git" or name==".env" or name.startswith(".env.") or name in {"id_rsa","id_ed25519"}:
            raise ValueError(f"sensitive Codex path is forbidden: {path}")
        if lower.endswith((".pem",".key",".p12",".pfx")):
            raise ValueError(f"sensitive Codex file type is forbidden: {path}")
        return p

    def _run_checked(self,argv:tuple[str,...],cwd:Path,env:dict[str,str],*,label:str,timeout:float|None=None)->str:
        try:
            code,stdout,stderr=self.runner(argv,cwd,env,timeout or self.config.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{label} timed out") from exc
        if code!=0:
            detail=(stderr or stdout or f"exit {code}").strip()[-4000:]
            raise RuntimeError(f"{label} failed: {detail}")
        return stdout

    def _clone(self,repository:str,root:Path)->Path:
        token=resolve_github_token(repository)
        askpass=root/"git-askpass.sh"
        askpass.write_text(
            "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' x-access-token ;; *) printf '%s\\n' \"$FACTORY_CODEX_GIT_TOKEN\" ;; esac\n",
            encoding="utf-8",
        )
        askpass.chmod(stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR)
        clone_env=dict(os.environ)
        clone_env.update({"GIT_ASKPASS":str(askpass),"GIT_TERMINAL_PROMPT":"0","FACTORY_CODEX_GIT_TOKEN":token})
        checkout=root/"repo"
        try:
            self._run_checked(("git","clone","--depth","1",f"https://github.com/{repository}.git",str(checkout)),root,clone_env,label="git clone",timeout=180)
        finally:
            askpass.unlink(missing_ok=True)
        return checkout

    @staticmethod
    def _prompt(item:DirectExecutionItem)->str:
        return (
            "You are the implementation executor inside AI Product Factory. Work only in this checkout. "
            "Read repository instructions such as AGENTS.md before editing. Do not commit, push, open PRs, "
            "inspect credentials, or modify .env/private-key files. Keep changes narrowly scoped. "
            "Run the repository's deterministic tests relevant to the change when feasible. "
            "Do not run the 63-question Agent SQL benchmark unless the task explicitly says to do so.\n\n"
            f"Project: {item.project_key}\nRepository: {item.repository}\nTask: {item.title}\n"
            f"Description:\n{item.description}\n"
        )

    def _changed_paths(self,checkout:Path)->tuple[str,...]:
        env=self._safe_codex_env()
        tracked=self._run_checked(("git","diff","--name-only","-z","HEAD"),checkout,env,label="git diff",timeout=60)
        untracked=self._run_checked(("git","ls-files","--others","--exclude-standard","-z"),checkout,env,label="git ls-files",timeout=60)
        names=[x for x in (tracked+"\0"+untracked).split("\0") if x]
        return tuple(dict.fromkeys(names))

    def _collect_patch(self,checkout:Path)->dict[str,str|None]:
        paths=self._changed_paths(checkout)
        if not paths:
            raise ValueError("Codex completed without repository changes")
        if len(paths)>self.config.max_files:
            raise ValueError(f"Codex changed {len(paths)} files; limit is {self.config.max_files}")
        patch:dict[str,str|None]={}
        total=0
        root=checkout.resolve()
        for raw in paths:
            p=self._validate_path(raw)
            full=(checkout/Path(*p.parts))
            resolved=full.resolve(strict=False)
            if root not in resolved.parents and resolved!=root:
                raise ValueError(f"Codex path escaped checkout: {raw}")
            if full.is_symlink():
                raise ValueError(f"Codex symlink changes are not supported: {raw}")
            if not full.exists():
                patch[raw]=None
                continue
            data=full.read_bytes()
            total+=len(data)
            if total>self.config.max_total_bytes:
                raise ValueError(f"Codex patch exceeds {self.config.max_total_bytes} bytes")
            try:
                patch[raw]=data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Codex binary change is not supported: {raw}") from exc
        return patch

    def produce(self,item:DirectExecutionItem)->ImplementationArtifact:
        if item.human_gate_required:
            raise PermissionError("task requires human approval before Codex execution")
        with tempfile.TemporaryDirectory(prefix="factory-codex-") as tmp:
            root=Path(tmp)
            checkout=self._clone(item.repository,root)
            env=self._safe_codex_env()
            stdout=self._run_checked(
                (self.config.executable,"exec","--json","--full-auto",self._prompt(item)),
                checkout,env,label="codex exec",
            )
            events=0
            for line in stdout.splitlines():
                if not line.strip(): continue
                try: json.loads(line)
                except json.JSONDecodeError as exc: raise ValueError("Codex --json emitted invalid JSONL") from exc
                events+=1
            self.last_trace_events=events
            files=self._collect_patch(checkout)

        title=item.title.strip() or "Codex implementation"
        short=title[:72]
        plan=(
            f"# Codex execution plan\n\nTask: {title}\n\n"
            "Implementation was produced in an isolated checkout by the bounded Codex CLI worker. "
            f"Changed files: {', '.join(sorted(files))}.\n"
        )
        body=(
            f"Implements factory task {item.task_id} using the Codex route.\n\n"
            "The Factory does not merge this PR automatically. CI, Preview applicability/evidence, "
            "and the human production merge gate remain authoritative."
        )
        return ImplementationArtifact(plan,files,f"feat(factory): {short}",short,body)
