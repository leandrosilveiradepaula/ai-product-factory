from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}
FORBIDDEN_PACKAGE_GLOBS = ("*", "?", "[", "]")
FORBIDDEN_VERSION_RANGE_TOKENS = ("*", "^", "~", ">", "<", "||", " ")


class AuditPolicyError(ValueError):
    pass


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AuditPolicyError("expires_at must be a non-empty ISO-8601 string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AuditPolicyError(f"invalid expires_at: {value}") from exc
    if parsed.tzinfo is None:
        raise AuditPolicyError("expires_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_policy(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if policy.get("schema_version") != 1:
        raise AuditPolicyError("unsupported dependency-audit policy schema_version")
    audit_level = policy.get("audit_level")
    if audit_level not in {"moderate", "high", "critical"}:
        raise AuditPolicyError("audit_level must be moderate, high, or critical")

    exceptions = policy.get("exceptions")
    if not isinstance(exceptions, list):
        raise AuditPolicyError("exceptions must be a list")

    by_package: dict[str, dict[str, Any]] = {}
    for item in exceptions:
        if not isinstance(item, dict):
            raise AuditPolicyError("each exception must be an object")
        package = item.get("package")
        version = item.get("installed_version")
        max_severity = item.get("max_severity")
        reason = item.get("reason")
        expires_at = item.get("expires_at")

        if not isinstance(package, str) or not package:
            raise AuditPolicyError("exception package must be a non-empty string")
        if any(token in package for token in FORBIDDEN_PACKAGE_GLOBS):
            raise AuditPolicyError(f"wildcards are forbidden in exception package: {package}")
        if package in by_package:
            raise AuditPolicyError(f"duplicate exception package: {package}")
        if not isinstance(version, str) or not version:
            raise AuditPolicyError(f"installed_version is required for {package}")
        if any(token in version for token in FORBIDDEN_VERSION_RANGE_TOKENS):
            raise AuditPolicyError(f"installed_version must be exact for {package}: {version}")
        if max_severity not in {"moderate", "high"}:
            raise AuditPolicyError(
                f"max_severity for {package} must be moderate or high; critical exceptions are forbidden"
            )
        if not isinstance(reason, str) or len(reason.strip()) < 20:
            raise AuditPolicyError(f"reason must explain the exception for {package}")
        _parse_time(expires_at)
        by_package[package] = item
    return by_package


def _installed_version(lockfile: dict[str, Any], package: str) -> str | None:
    packages = lockfile.get("packages")
    if not isinstance(packages, dict):
        raise AuditPolicyError("package-lock.json is missing packages")
    node = packages.get(f"node_modules/{package}")
    if not isinstance(node, dict):
        return None
    version = node.get("version")
    return version if isinstance(version, str) else None


def evaluate_dependency_audit(
    audit_report: dict[str, Any],
    lockfile: dict[str, Any],
    policy: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[list[str], list[str]]:
    exceptions = _validate_policy(policy)
    if audit_report.get("auditReportVersion") != 2:
        raise AuditPolicyError("npm audit report is missing auditReportVersion=2")
    vulnerabilities = audit_report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise AuditPolicyError("npm audit report is missing vulnerabilities")

    audit_level = policy["audit_level"]
    threshold = SEVERITY_RANK[audit_level]
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    violations: list[str] = []
    accepted: list[str] = []

    for package, finding in sorted(vulnerabilities.items()):
        if not isinstance(finding, dict):
            violations.append(f"{package}: malformed vulnerability entry")
            continue
        severity = finding.get("severity")
        if severity not in SEVERITY_RANK:
            violations.append(f"{package}: unknown severity {severity!r}")
            continue
        if SEVERITY_RANK[severity] < threshold:
            continue

        exception = exceptions.get(package)
        if exception is None:
            violations.append(f"{package}: {severity} vulnerability has no approved exception")
            continue

        installed = _installed_version(lockfile, package)
        expected = exception["installed_version"]
        if installed != expected:
            violations.append(
                f"{package}: installed version {installed!r} does not match exception version {expected!r}"
            )
            continue

        expires_at = _parse_time(exception["expires_at"])
        if current_time >= expires_at:
            violations.append(
                f"{package}@{installed}: exception expired at {exception['expires_at']}"
            )
            continue

        allowed_rank = SEVERITY_RANK[exception["max_severity"]]
        if SEVERITY_RANK[severity] > allowed_rank:
            violations.append(
                f"{package}@{installed}: severity {severity} exceeds exception ceiling "
                f"{exception['max_severity']}"
            )
            continue

        accepted.append(
            f"{package}@{installed}: {severity} accepted until {exception['expires_at']}"
        )

    return violations, accepted


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditPolicyError(f"cannot read valid JSON from {path}") from exc
    if not isinstance(value, dict):
        raise AuditPolicyError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce the Console dependency audit policy.")
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        report = _load_json(args.audit)
        lockfile = _load_json(args.lock)
        policy = _load_json(args.policy)
        violations, accepted = evaluate_dependency_audit(report, lockfile, policy)
    except AuditPolicyError as exc:
        print(f"DEPENDENCY_AUDIT_POLICY_ERROR: {exc}")
        return 1

    for item in accepted:
        print(f"DEPENDENCY_AUDIT_EXCEPTION: {item}")
    if violations:
        for item in violations:
            print(f"DEPENDENCY_AUDIT_VIOLATION: {item}")
        print(f"DEPENDENCY_AUDIT_FAILED={len(violations)}")
        return 1

    print("CONSOLE_DEPENDENCY_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
