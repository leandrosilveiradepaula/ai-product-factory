"""Fail-closed, read-only monotonicity check for durable Block 1 certificates.

This is an alarm, never a source of PASS. It compares the exact persisted
current main SHA to the immediately previous persisted assessment and refuses
to hide *any* individually regressed criterion behind a stable total count.
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Callable

from ai_product_factory.admission_diagnostics import SupabaseAdmissionReader
from ai_product_factory.product_readiness import REQUIRED_COVERAGE_BY_DOMAIN

REPO = "leandrosilveiradepaula/ai-product-factory"
SHA = re.compile(r"[0-9a-f]{40}\\Z")
EXPECTED = {(domain, name) for domain, keys in REQUIRED_COVERAGE_BY_DOMAIN.items()
            for name in keys}
STATUSES = frozenset({"passed", "partial", "missing", "failed", "external_gate"})


class CertificationRegression(RuntimeError):
    pass


def _criteria(record: object) -> tuple[str, dict[tuple[str, str], str]]:
    if not isinstance(record, dict) or record.get("state") != "persisted":
        raise CertificationRegression("certificate_unverified")
    sha = record.get("assessed_commit")
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise CertificationRegression("certificate_sha_invalid")
    report = record.get("report")
    source = report.get("criteria") if isinstance(report, dict) else None
    if not isinstance(source, dict) or set(source) != set(REQUIRED_COVERAGE_BY_DOMAIN):
        raise CertificationRegression("certificate_domain_inventory_invalid")
    cells = {}
    for domain, keys in REQUIRED_COVERAGE_BY_DOMAIN.items():
        items = source.get(domain)
        if not isinstance(items, dict) or set(items) != set(keys):
            raise CertificationRegression("certificate_criterion_inventory_invalid")
        for key in keys:
            row = items[key]
            status = row.get("status") if isinstance(row, dict) else None
            if status not in STATUSES:
                raise CertificationRegression("certificate_status_invalid")
            cells[(domain, key)] = status
    if set(cells) != EXPECTED or len(cells) != 19:
        raise CertificationRegression("certificate_inventory_incomplete")
    return sha, cells


def compare_certifications(rows: object, expected_sha: str) -> dict:
    if not isinstance(expected_sha, str) or SHA.fullmatch(expected_sha) is None:
        raise CertificationRegression("expected_sha_invalid")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2:
        raise CertificationRegression("certification_history_unavailable")
    current_sha, current = _criteria(rows[0])
    if current_sha != expected_sha:
        raise CertificationRegression("current_main_certificate_not_persisted")
    previous = {}
    previous_sha = None
    if len(rows) == 2:
        previous_sha, previous = _criteria(rows[1])
        if previous_sha == current_sha:
            raise CertificationRegression("duplicate_sha_certification_history")
    regressed = sorted("%s/%s" % cell for cell in previous
                       if previous[cell] == "passed" and current[cell] != "passed")
    gained = sorted("%s/%s" % cell for cell in current
                    if current[cell] == "passed" and previous.get(cell) != "passed")
    return {
        "schema": "factory-block1-certified-criterion-delta-v1",
        "assessed_commit": current_sha,
        "previous_commit": previous_sha,
        "previous_passed": sum(v == "passed" for v in previous.values()),
        "current_passed": sum(v == "passed" for v in current.values()),
        "current_partial": sum(v == "partial" for v in current.values()),
        "current_missing": sum(v == "missing" for v in current.values()),
        "regressed": regressed,
        "newly_passed": gained,
        "monotonic": not regressed,
        "product_ready_claimed": False,
        "independent_certification_replaced": False,
        "writes": 0,
        "paid_calls": 0,
    }


def collect(get: Callable[[str], object], expected_sha: str) -> dict:
    # Read only the two most recent durable reports; no read of secret/operator
    # records. Row count and identity are checked before evaluating any status.
    path = ("factory_product_readiness_certifications"
            "?select=repository,assessed_commit,state,report"
            "&repository=eq." + REPO
            + "&state=eq.persisted&order=created_at.desc&limit=2")
    rows = get(path)
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or row.get("repository") != REPO for row in rows
    ):
        raise CertificationRegression("certificate_repository_invalid")
    return compare_certifications(rows, expected_sha)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Block 1 regression alarm")
    parser.add_argument("--assessed-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = collect(SupabaseAdmissionReader()._get, args.assessed_commit)
    except (CertificationRegression, ValueError, RuntimeError, OSError, KeyError,
            TypeError, UnicodeError):
        # Do not log provider bodies, operator PII, credentials or tokens.
        print(json.dumps({"schema": "factory-block1-certified-criterion-delta-v1",
                          "status": "unverifiable", "monotonic": False}))
        return 2
    from pathlib import Path
    output = Path(args.output)
    output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "assessed_commit", "previous_passed", "current_passed",
        "regressed", "newly_passed", "monotonic"
    )}, sort_keys=True))
    return 0 if result["monotonic"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
