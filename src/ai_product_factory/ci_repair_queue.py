from __future__ import annotations

"""Durable, exact-SHA CI repair requests.

This module deliberately does not execute a patch.  A successful enqueue
materializes a bounded Change Set work unit in the Control Plane; the existing
Direct/Codex routing, budget, epoch and lease controls then own execution.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote

from .ci_followup_queue import CIFollowupItem
from .github_rest import GitHubCheckFailure
from .supabase_server import resolve_supabase_server_config


_SHA = re.compile(r"[0-9a-f]{40}")
_CLASSES = frozenset({"code", "infrastructure", "runner", "permission", "quota", "unknown"})


@dataclass(frozen=True)
class DurableCIFailure:
    """Sanitized failure evidence that is safe to retain in the Control Plane."""

    name: str
    conclusion: str
    failure_class: str
    details_url: str | None = None
    summary: str | None = None

    @classmethod
    def from_github(cls, failure: GitHubCheckFailure) -> "DurableCIFailure":
        return cls(
            name=failure.name,
            conclusion=failure.conclusion,
            failure_class=failure.failure_class,
            details_url=failure.details_url,
            summary=failure.summary,
        )

    def as_dict(self) -> dict[str, str]:
        payload = {
            "name": self.name[:240],
            "conclusion": self.conclusion[:80],
            "failure_class": self.failure_class,
        }
        if self.details_url:
            payload["details_url"] = self.details_url[:1000]
        if self.summary:
            payload["summary"] = self.summary[:2000]
        return payload


class SupabaseCIRepairQueue:
    """Service-role RPC client for the CI repair handoff.

    The database transaction is authoritative for candidate identity,
    generation, idempotency and work-unit materialization.  This client does
    no optimistic status writes that could survive a pause or a moved PR head.
    """

    def __init__(self, *, url: str | None = None, secret_key: str | None = None, service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(url=url, secret_key=secret_key, service_role_key=service_role_key)
        self.url = cfg.url
        self.headers = cfg.headers

    def _rpc(self, name: str, payload: dict) -> dict:
        request_data = json.dumps(payload).encode("utf-8")
        request_headers = {**self.headers, "Content-Type": "application/json"}
        request_obj = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}", data=request_data,
            headers=request_headers, method="POST",
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # A missing migration is deliberately a closed gate, never a
            # fallback to a local/ephemeral repair loop.
            raise RuntimeError(f"CI repair control-plane RPC failed: {name} ({exc.code})") from exc
        try:
            data = json.loads(raw) if raw else None
        except ValueError as exc:
            raise RuntimeError("CI repair control-plane RPC returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("CI repair control-plane RPC returned no object")
        return data

    @staticmethod
    def _validate(item: CIFollowupItem, failures: Iterable[DurableCIFailure]) -> tuple[DurableCIFailure, ...]:
        if not _SHA.fullmatch(item.candidate_commit):
            raise ValueError("CI repair requires an exact lowercase candidate SHA")
        if not item.change_set_id or not item.project_id:
            raise ValueError("CI repair requires a durable Change Set and project identity")
        if item.execution_generation is None or item.execution_generation < 1:
            raise ValueError("CI repair requires an execution generation")
        values = tuple(failures)
        if not 1 <= len(values) <= 20:
            raise ValueError("CI repair requires between one and twenty failures")
        for failure in values:
            if (not failure.name.strip() or not failure.conclusion.strip()
                    or failure.failure_class not in _CLASSES):
                raise ValueError("invalid sanitized CI failure")
        return values

    def enqueue_failure(self, *, item: CIFollowupItem, failures: Iterable[DurableCIFailure], max_attempts: int = 3) -> dict:
        values = self._validate(item, failures)
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError("CI repair max_attempts must be between one and three")
        failure_class = values[0].failure_class
        if any(value.failure_class != failure_class for value in values):
            failure_class = "unknown"
        return self._rpc("factory_enqueue_ci_repair", {
            "p_source_run_id": item.run_id,
            "p_project_id": item.project_id,
            "p_change_set_id": item.change_set_id,
            "p_repository": item.repository,
            "p_pr_number": item.pr_number,
            "p_branch": item.branch,
            "p_candidate_commit": item.candidate_commit,
            "p_execution_generation": item.execution_generation,
            "p_failure_class": failure_class,
            "p_failures": [value.as_dict() for value in values],
            "p_max_attempts": max_attempts,
        })

    def record_ci_result(self, *, run_id: str, candidate_commit: str, status: str) -> dict:
        if not run_id.strip() or not _SHA.fullmatch(candidate_commit):
            raise ValueError("CI repair result requires exact run and candidate identities")
        if status not in {"passed", "failed"}:
            raise ValueError("CI repair result must be passed or failed")
        result = self._rpc("factory_record_ci_repair_result", {
            "p_release_run_id": run_id,
            "p_candidate_commit": candidate_commit,
            "p_status": status,
        })
        if type(result.get("updated")) is not bool:
            raise RuntimeError("CI repair result response is missing updated flag")
        if result["updated"]:
            if result.get("status") != status or not isinstance(result.get("repair_request_id"), str):
                raise RuntimeError("CI repair result response has invalid durable receipt")
        elif result.get("reason") != "no_awaiting_ci_repair":
            raise RuntimeError("CI repair result response has invalid no-op reason")
        return result

    def has_release_repair(self, *, run_id: str, candidate_commit: str) -> bool:
        """Compatibility read: pre-migration normal CI must keep flowing."""
        if not run_id.strip() or not _SHA.fullmatch(candidate_commit):
            raise ValueError("CI repair lookup requires exact run and candidate identities")
        path = (
            "factory_ci_repair_requests?select=id&release_run_id=eq."
            + quote(run_id, safe="") + "&repaired_commit=eq."
            + quote(candidate_commit, safe="") + "&status=eq.awaiting_ci&limit=1"
        )
        request_obj = urllib.request.Request(f"{self.url}/rest/v1/{path}", headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request_obj, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise RuntimeError(f"CI repair control-plane lookup failed ({exc.code})") from exc
        try:
            rows = json.loads(raw) if raw else []
        except ValueError as exc:
            raise RuntimeError("CI repair control-plane lookup returned invalid JSON") from exc
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("CI repair control-plane lookup returned invalid rows")
        return bool(rows)
