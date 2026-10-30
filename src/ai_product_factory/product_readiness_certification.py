"""Independent, deterministic producer for durable product-readiness evidence.

The global readiness observer deliberately does not write.  This module is the
separate producer: it verifies the immutable repository/CI context, translates
the 19 criterion records into the six-domain contract, and produces a report
that may safely be persisted as *not ready*.  It never starts development work,
uses a model, or grants release authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Callable

from .product_readiness import REQUIRED_COVERAGE_BY_DOMAIN, assess_product_readiness

SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
CRITERION_STATES = frozenset({"passed", "partial", "missing", "failed", "external_gate"})


class CertificationEvidenceError(RuntimeError):
    """The source snapshot cannot support a durable assessment."""


def canonical_evidence_digest(value: object) -> str:
    """Stable request identity; rejects lossy/non-JSON input before a write."""
    try:
        body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CertificationEvidenceError("evidence manifest is not canonical JSON") from exc
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def _require_sha(value: object) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise CertificationEvidenceError("exact 40-character SHA required")
    return value


def _source_snapshot(*, repository: str, assessed_commit: str, github_get: Callable[[str], object]) -> dict:
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise CertificationEvidenceError("invalid repository")
    sha = _require_sha(assessed_commit)
    prefix = "/repos/" + repository
    repo = github_get(prefix)
    branch = repo.get("default_branch") if isinstance(repo, dict) else None
    if not isinstance(branch, str) or not branch:
        raise CertificationEvidenceError("repository default branch is unavailable")
    ref = github_get(prefix + "/git/ref/heads/" + branch)
    if not isinstance(ref, dict) or (ref.get("object") or {}).get("sha") != sha:
        raise CertificationEvidenceError("repository HEAD changed or does not match assessment")
    runs = github_get(prefix + "/actions/runs?head_sha=" + sha + "&event=push&per_page=100")
    rows = runs.get("workflow_runs") if isinstance(runs, dict) else None
    if (not isinstance(rows, list) or type(runs.get("total_count")) is not int
            or len(rows) != runs["total_count"] or not rows or len(rows) > 100):
        raise CertificationEvidenceError("incomplete exact-SHA workflow inventory")
    valid = [row for row in rows if isinstance(row, dict) and row.get("name") == "validate"
             and row.get("path") == ".github/workflows/validate.yml"
             and row.get("event") == "push" and row.get("head_sha") == sha
             and row.get("head_branch") == branch and row.get("status") == "completed"
             and row.get("conclusion") == "success" and type(row.get("id")) is int]
    if len(valid) != 1:
        raise CertificationEvidenceError("one successful exact-SHA validate workflow is required")
    run_id = valid[0]["id"]
    jobs = github_get(prefix + "/actions/runs/" + str(run_id) + "/jobs?per_page=100")
    job_rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    if (not isinstance(job_rows, list) or type(jobs.get("total_count")) is not int
            or len(job_rows) != jobs["total_count"] or not job_rows or len(job_rows) > 100):
        raise CertificationEvidenceError("incomplete validation job evidence")
    names = set()
    for job in job_rows:
        if (not isinstance(job, dict) or job.get("run_id") != run_id or job.get("head_sha") != sha
                or job.get("status") != "completed" or job.get("conclusion") != "success"
                or not isinstance(job.get("name"), str)):
            raise CertificationEvidenceError("validation job is not executed for the assessment SHA")
        names.add(job["name"])
    if not {"test", "factory-acceptance"}.issubset(names):
        raise CertificationEvidenceError("required validation jobs are missing")
    return {"repository": repository, "branch": branch, "assessed_commit": sha,
            "validation_run_id": run_id, "validation_jobs": sorted(names),
            "verification_state": "executed_same_SHA"}


def _exact_ci_attestation(*, snapshot: dict) -> dict:
    """The only current automatic PASS provider: executed exact-SHA CI jobs.

    A manifest can request this provider, but cannot supply its contents.
    The verified source is built from separately fetched GitHub workflow/jobs.
    Other domains REQUIRE their own future independent source verifiers.
    """
    return {
        "kind": "github_exact_sha_validate",
        "repository": snapshot["repository"],
        "assessed_commit": snapshot["assessed_commit"],
        "run_id": snapshot["validation_run_id"],
        "jobs": snapshot["validation_jobs"],
    }


def _criterion(raw: object, *, domain: str, key: str, snapshot: dict) -> dict:
    if not isinstance(raw, dict):
        return {"status": "missing", "evidence": [], "reason": "criterion record is required"}
    status = raw.get("status")
    reason = raw.get("reason")
    evidence = raw.get("evidence")
    verification = raw.get("verification_state")
    if not isinstance(status, str) or status not in CRITERION_STATES:
        return {"status": "missing", "evidence": [], "reason": "invalid criterion status"}
    if not isinstance(reason, str):
        reason = ""
    if (not isinstance(evidence, list)
            or any(not isinstance(x, str) or not x.strip() for x in evidence)):
        return {"status": "missing", "evidence": [], "reason": "malformed evidence"}
    if not isinstance(verification, str) or not verification.strip():
        return {"status": "missing", "evidence": evidence, "reason": "verification state is required"}

    if status == "passed":
        # SHA-bearing URLs, prose, an assertion of "reviewed", or an arbitrary
        # GitHub run number are NOT independently authenticated evidence.
        # The only currently executable scope verifier is exact-SHA test CI.
        attestation = raw.get("attestation")
        expected = _exact_ci_attestation(snapshot=snapshot)
        if ((domain, key) != ("test_strategy", "unit_integration")
                or not isinstance(attestation, dict)
                or attestation != expected):
            return {
                "status": "failed",
                "evidence": [],
                "reason": "no independently verified source for passing criterion",
                "verification_state": verification.strip(),
                "domain": domain,
                "criterion": key,
            }
        sha = snapshot["assessed_commit"]
        # Do not copy caller-provided evidence into a positive certificate.
        # Derive the citation from the GitHub HEAD+run+jobs checked above.
        evidence = [
            "https://github.com/" + snapshot["repository"]
            + "/actions/runs/" + str(snapshot["validation_run_id"]) + "#sha=" + sha
        ]
        return {
            "status": "passed",
            "evidence": evidence,
            "reason": "successful exact-SHA validate/test/factory-acceptance verified by GitHub",
            "verification_state": verification.strip(),
            "domain": domain,
            "criterion": key,
            "attestation": expected,
        }
    return {
        "status": status,
        "evidence": evidence,
        "reason": reason.strip(),
        "verification_state": verification.strip(),
        "domain": domain,
        "criterion": key,
    }


def conservative_verified_manifest(*, repository: str, assessed_commit: str,
                                   github_get: Callable[[str], object]) -> dict:
    """Build a repeatable 19-criterion baseline WITHOUT invented PASS results.

    Only exact-SHA CI test/acceptance is independently verified here.
    All other criteria stay missing until an applicable trusted source verifier
    is implemented and actually executed; a healthy endpoint or document
    inventory may be described separately, but cannot become a domain PASS.
    """
    snapshot = _source_snapshot(repository=repository, assessed_commit=assessed_commit,
                                github_get=github_get)
    domain_verification = {
        "security": "reviewed",
        "observability_operations": "observed",
        "test_strategy": "executed",
        "product_experience": "observed",
        "documentation": "reviewed",
        "functional_completeness": "reviewed",
    }
    criteria = {}
    for domain, keys in REQUIRED_COVERAGE_BY_DOMAIN.items():
        criteria[domain] = {
            key: {
                "status": "missing",
                "reason": "no independent executable proof for " + domain + "/" + key,
                "evidence": [],
                "verification_state": domain_verification[domain],
            }
            for key in keys
        }
    criteria["test_strategy"]["unit_integration"] = {
        "status": "passed",
        "reason": "executed exact-SHA unit/integration and acceptance CI",
        "evidence": [],
        "verification_state": "executed",
        "attestation": _exact_ci_attestation(snapshot=snapshot),
    }
    # The exact CI run proves these checks executed, not that the main ruleset
    # protects PostgreSQL QA, E2E, browser, or all multi-project regressions.
    criteria["test_strategy"]["regression_gates"] = {
        "status": "partial",
        "reason": "CI executed, but complete enforced release and migration QA gates need independent review",
        "evidence": [
            "https://github.com/" + repository
            + "/actions/runs/" + str(snapshot["validation_run_id"])
            + "#sha=" + snapshot["assessed_commit"]
        ],
        "verification_state": "executed",
    }
    return {"schema_version": 1, "criteria": criteria}


@dataclass(frozen=True)
class CertificationReport:
    assessment: object
    report: dict
    evidence_digest: str


def certify_product_readiness(*, repository: str, assessed_commit: str, manifest: object,
                              github_get: Callable[[str], object]) -> CertificationReport:
    """Collect a source snapshot and deterministically evaluate all 19 criteria.

    The manifest is evidence supplied by independently executed checks/reviews;
    this function validates its shape and immutable SHA binding, rather than
    treating a green workflow as a complete product certificate.
    """
    snapshot = _source_snapshot(repository=repository, assessed_commit=assessed_commit,
                                github_get=github_get)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("criteria"), dict):
        raise CertificationEvidenceError("criteria manifest is required")
    evidence_digest = canonical_evidence_digest({"snapshot": snapshot, "manifest": manifest})
    criteria = manifest["criteria"]
    domains, criteria_report, blockers = {}, {}, []
    for domain, required in REQUIRED_COVERAGE_BY_DOMAIN.items():
        raw_domain = criteria.get(domain)
        rows = raw_domain if isinstance(raw_domain, dict) else {}
        per_domain = {}
        passed = True
        evidence, verification = [], []
        for key in required:
            item = _criterion(rows.get(key), domain=domain, key=key, snapshot=snapshot)
            per_domain[key] = item
            evidence.extend(item["evidence"])
            verification.append(item.get("verification_state", ""))
            if item["status"] != "passed":
                passed = False
                blockers.append(f"{domain}/{key}: {item['status']} {item['reason']}".strip())
        criteria_report[domain] = per_domain
        # The official six-domain evaluator retains its stricter vocabulary.
        allowed = {"security": {"executed", "reviewed"},
                   "observability_operations": {"executed", "observed"},
                   "test_strategy": {"executed"}, "product_experience": {"observed", "reviewed"},
                   "documentation": {"reviewed"},
                   "functional_completeness": {"executed", "observed", "reviewed"}}[domain]
        if any(value not in allowed for value in verification):
            passed = False
            blockers.append(f"{domain}: criterion verification_state is not valid for this domain")
        domains[domain] = {"status": "passed" if passed else "failed",
                           "reason": "" if passed else "one or more required criteria are not passed",
                           "evidence": sorted(set(evidence)), "coverage": list(required),
                           "verification_state": next((x for x in verification if x in allowed), "")}
    assessment = assess_product_readiness(assessed_commit=snapshot["assessed_commit"],
        assessment_ref="product-readiness-certifier:" + evidence_digest,
        domains=domains, critical_blockers=tuple(blockers))
    report = {"schema_version": 1, "scope": "entire_product_at_exact_current_head",
              "source_snapshot": snapshot, "criteria": criteria_report,
              "assessment": assessment.as_result(), "writes": 0, "paid_calls": 0}
    return CertificationReport(assessment=assessment, report=report,
                               evidence_digest=evidence_digest)
