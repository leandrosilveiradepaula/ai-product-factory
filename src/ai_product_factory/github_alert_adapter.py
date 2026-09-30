from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .operational_alerts import OperationalAlert


class AlertIssueClient(Protocol):
    def find_open_issue_containing(self, marker: str):
        ...

    def create_issue(self, *, title: str, body: str):
        ...

    def close_issue(self, issue_number: int) -> None:
        ...


@dataclass(frozen=True)
class AlertPublishResult:
    code: str
    created: bool
    issue_number: int
    issue_url: str


@dataclass(frozen=True)
class AlertResolveResult:
    code: str
    issue_number: int
    issue_url: str


class GitHubIssueAlertAdapter:
    """Optional operational-alert sink backed by GitHub Issues.

    The adapter is intentionally passive: callers must invoke publish/resolve.
    It never schedules itself and only closes issues with deterministic known markers.
    """

    def __init__(self, client: AlertIssueClient) -> None:
        self.client = client

    @staticmethod
    def marker(alert: OperationalAlert) -> str:
        return f"<!-- factory-alert:{alert.code} -->"

    def publish(self, alert: OperationalAlert) -> AlertPublishResult:
        marker = self.marker(alert)
        existing = self.client.find_open_issue_containing(marker)
        if existing is not None:
            return AlertPublishResult(
                code=alert.code,
                created=False,
                issue_number=existing.number,
                issue_url=existing.html_url,
            )

        title = f"[factory alert][{alert.severity}] {alert.code}"
        body = (
            f"{marker}\n"
            "Automated operational alert from AI Product Factory.\n\n"
            f"- Code: {alert.code}\n"
            f"- Severity: {alert.severity}\n"
            f"- Message: {alert.message}\n"
        )
        created = self.client.create_issue(title=title, body=body)
        return AlertPublishResult(
            code=alert.code,
            created=True,
            issue_number=created.number,
            issue_url=created.html_url,
        )

    def publish_many(self, alerts: tuple[OperationalAlert, ...]) -> tuple[AlertPublishResult, ...]:
        return tuple(self.publish(alert) for alert in alerts)

    def resolve_inactive(
        self,
        *,
        active_codes: set[str],
        known_codes: tuple[str, ...],
    ) -> tuple[AlertResolveResult, ...]:
        resolved: list[AlertResolveResult] = []
        for code in known_codes:
            if code in active_codes:
                continue
            marker=f"<!-- factory-alert:{code} -->"
            existing=self.client.find_open_issue_containing(marker)
            if existing is None:
                continue
            self.client.close_issue(existing.number)
            resolved.append(
                AlertResolveResult(
                    code=code,
                    issue_number=existing.number,
                    issue_url=existing.html_url,
                )
            )
        return tuple(resolved)
