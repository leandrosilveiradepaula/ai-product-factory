from __future__ import annotations

import argparse
import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote
from typing import Callable

from .github_rest import GitHubRestAdapter, GitHubPullRequest
from .supabase_issue_binding import SupabaseIssueBindingStore
from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class ManualCodexItem:
    run_id: str
    task_id: str
    project_key: str
    repository: str
    issue_number: int | None
    title: str
    description: str
    codex_level: int


GitHubFactory = Callable[[str], GitHubRestAdapter]


def run_marker(run_id: str) -> str:
    return f"Factory run: {run_id}"


class SupabaseManualCodexQueue:
    """Durable queue boundary for manual Codex handoff and PR adoption."""

    def __init__(
        self,
        *,
        url: str | None = None,
        secret_key: str | None = None,
        service_role_key: str | None = None,
    ) -> None:
        cfg = resolve_supabase_server_config(
            url=url,
            secret_key=secret_key,
            service_role_key=service_role_key,
        )
        self.url = cfg.url
        self.headers = cfg.headers

    def _get(self, path: str) -> list[dict]:
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{path}",
            headers=self.headers,
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def _rpc(self, name: str, payload: dict) -> dict | None:
        req = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",
            data=json.dumps(payload).encode(),
            headers={**self.headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    @staticmethod
    def _item(data: dict) -> ManualCodexItem:
        issue = data.get("issue_number")
        return ManualCodexItem(
            run_id=str(data["run_id"]),
            task_id=str(data["task_id"]),
            project_key=str(data["project_key"]),
            repository=str(data["repository"]),
            issue_number=int(issue) if issue else None,
            title=str(data["title"]),
            description=str(data.get("description") or ""),
            codex_level=int(data.get("codex_level") or 1),
        )

    def claim_next(self, worker_id: str) -> ManualCodexItem | None:
        data = self._rpc(
            "factory_claim_next_manual_codex_handoff",
            {"p_worker_id": worker_id},
        )
        return None if data is None else self._item(data)

    def mark_waiting(self, run_id: str) -> dict:
        data = self._rpc(
            "factory_mark_manual_codex_waiting",
            {"p_run_id": run_id},
        )
        if data is None:
            raise RuntimeError("manual Codex handoff did not persist waiting state")
        return data

    def next_waiting(self) -> ManualCodexItem | None:
        runs = self._get(
            "factory_runs?select=id,task_id,metadata&status=eq.awaiting_codex_manual"
            "&execution_route=eq.codex&order=created_at.asc&limit=1"
        )
        if not runs:
            return None

        run = runs[0]
        run_id = str(run["id"])
        task_id = str(run["task_id"])
        metadata = run.get("metadata") or {}
        issue_data = metadata.get("github_issue") or {}
        issue_number = int(issue_data.get("number") or 0)
        if issue_number < 1:
            raise RuntimeError("awaiting manual Codex run is missing GitHub issue binding")

        tasks = self._get(
            f"factory_tasks?select=project_id,title,description&id=eq.{quote(task_id)}&limit=1"
        )
        if not tasks:
            raise RuntimeError("manual Codex run task was not found")
        task = tasks[0]
        project_id = str(task["project_id"])

        projects = self._get(
            f"factory_projects?select=project_key,repository&id=eq.{quote(project_id)}&limit=1"
        )
        if not projects or not projects[0].get("repository"):
            raise RuntimeError("manual Codex project repository is not configured")
        project = projects[0]

        return ManualCodexItem(
            run_id=run_id,
            task_id=task_id,
            project_key=str(project["project_key"]),
            repository=str(project["repository"]),
            issue_number=issue_number,
            title=str(task.get("title") or "Factory task"),
            description=str(task.get("description") or ""),
            codex_level=int(metadata.get("codex_level") or 1),
        )

    def adopt_pr(self, item: ManualCodexItem, pr: GitHubPullRequest) -> dict:
        if not pr.head_ref:
            raise RuntimeError("manual Codex PR is missing its head branch")
        data = self._rpc(
            "factory_adopt_manual_codex_pr",
            {
                "p_run_id": item.run_id,
                "p_pr_number": pr.number,
                "p_pr_url": pr.html_url,
                "p_head_sha": pr.head_sha,
                "p_head_ref": pr.head_ref,
            },
        )
        if data is None:
            raise RuntimeError("manual Codex PR adoption returned no evidence")
        return data


def _default_github_factory(repository: str) -> GitHubRestAdapter:
    return GitHubRestAdapter(repository=repository)


def _issue_body(item: ManualCodexItem) -> str:
    marker = run_marker(item.run_id)
    return (
        "## Manual Codex handoff\n\n"
        f"{marker}\n\n"
        f"Project: {item.project_key}\n"
        f"Factory task: {item.task_id}\n"
        f"Codex policy level: {item.codex_level}\n\n"
        "### Task\n\n"
        f"{item.description.strip() or item.title}\n\n"
        "### What the operator does\n\n"
        "Open Codex with the managed ChatGPT Business account and ask it to implement this GitHub issue. "
        "Codex should work on a branch and open a pull request to main.\n\n"
        "The pull request body must contain this exact marker so the Factory can resume automatically:\n\n"
        f"{marker}\n\n"
        "Do not merge the pull request. The Factory will resume CI, Preview and the human production release gate.\n\n"
        "Do not run the Agent SQL 63-question benchmark unless a future task explicitly authorizes it."
    )


def prepare_once(
    worker_id: str,
    *,
    queue: SupabaseManualCodexQueue | None = None,
    binding: SupabaseIssueBindingStore | None = None,
    github_factory: GitHubFactory = _default_github_factory,
) -> dict:
    if os.getenv("FACTORY_CODEX_ENABLED", "").strip().lower() == "true":
        return {
            "claimed": False,
            "status": "blocked",
            "reason": "automatic_codex_enabled",
        }
    if os.getenv("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED", "true").strip().lower() == "false":
        return {
            "claimed": False,
            "status": "blocked",
            "reason": "manual_codex_fallback_disabled",
        }

    queue = queue or SupabaseManualCodexQueue()
    item = queue.claim_next(worker_id)
    if item is None:
        return {"claimed": False, "status": "empty"}

    github = github_factory(item.repository)
    marker = run_marker(item.run_id)

    if item.issue_number is not None:
        issue = github.get_issue(item.issue_number)
    else:
        issue = github.find_open_issue_containing(marker)
        if issue is None:
            issue = github.create_issue(title=f"[codex-manual] {item.title}", body=_issue_body(item))
        (binding or SupabaseIssueBindingStore()).bind_issue(run_id=item.run_id, issue=issue)

    queue.mark_waiting(item.run_id)
    return {
        "claimed": True,
        "status": "awaiting_codex_manual",
        "run_id": item.run_id,
        "issue_number": issue.number,
        "issue_url": issue.html_url,
        "marker": marker,
    }


def followup_once(
    *,
    queue: SupabaseManualCodexQueue | None = None,
    github_factory: GitHubFactory = _default_github_factory,
) -> dict:
    queue = queue or SupabaseManualCodexQueue()
    item = queue.next_waiting()
    if item is None:
        return {"claimed": False, "status": "empty"}

    github = github_factory(item.repository)
    marker = run_marker(item.run_id)
    pr = github.find_open_pull_request_containing(marker)
    if pr is None:
        return {
            "claimed": True,
            "status": "awaiting_codex_manual",
            "run_id": item.run_id,
            "issue_number": item.issue_number,
            "marker": marker,
        }

    if pr.base_ref and pr.base_ref != "main":
        return {
            "claimed": True,
            "status": "blocked",
            "run_id": item.run_id,
            "pr_number": pr.number,
            "error": "manual Codex PR must target main",
        }

    adopted = queue.adopt_pr(item, pr)
    return {
        "claimed": True,
        "status": str(adopted.get("status") or "ci_pending"),
        "run_id": item.run_id,
        "pr_number": pr.number,
        "candidate_commit": pr.head_sha,
        "branch": pr.head_ref,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("prepare", "followup"), required=True)
    parser.add_argument(
        "--worker-id",
        default=f"manual-codex-{socket.gethostname()}",
    )
    args = parser.parse_args()

    try:
        if args.mode == "prepare":
            out = prepare_once(args.worker_id)
        else:
            out = followup_once()
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
