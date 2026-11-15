#!/usr/bin/env python3
"""Operator-dispatched B4 infrastructure recovery; read-only unless --execute.

The CLI is intentionally NEVER invoked by cron, the ordinary specialist
retry worker, release-followup or the product-readiness certifier. Even the
explicit execute path can only requeue the already audited, original jobs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from ai_product_factory.github_auth import resolve_github_token
from ai_product_factory.specialist_infrastructure_recovery import (
    FACTORY_REPOSITORY, SpecialistInfrastructureRecoveryBlocked,
    verify_recovery_sources,
)
from ai_product_factory.specialist_lane_queue import SupabaseSpecialistLaneQueue


def github_get(repository: str, path: str) -> dict:
    # resolve_github_token refuses cross-repo GITHUB_TOKEN inside Actions.
    token = resolve_github_token(repository)
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--reason-code", default="candidate_reconciliation_fix")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    # The workflow identity is a separate gate from service-role SQL ACL.
    # Never allow an arbitrary PR checkout or foreign Actions runner to
    # replay a terminal run with a service-role key.
    if (os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_REPOSITORY") != FACTORY_REPOSITORY
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise SystemExit("SPECIALIST_RECOVERY_WORKFLOW_IDENTITY_DENIED")
    if args.execute and os.environ.get("FACTORY_SPECIALIST_INFRA_EXECUTE") != "true":
        raise SystemExit("SPECIALIST_RECOVERY_EXECUTE_NOT_AUTHORIZED")

    factory_sha = os.environ.get("GITHUB_SHA", "")
    queue = SupabaseSpecialistLaneQueue()
    try:
        sources = verify_recovery_sources(
            read=queue._get, github_get=github_get,
            run_id=args.run_id,
            candidate_sha=args.candidate_sha, factory_sha=factory_sha,
        )
    except (SpecialistInfrastructureRecoveryBlocked, RuntimeError,
            ValueError, KeyError, TypeError, OSError) as exc:
        # Provider response content, tokens, arbitrary exception strings and
        # user data are never written to the workflow log.
        code = (str(exc) if isinstance(exc, SpecialistInfrastructureRecoveryBlocked)
                else "source_provider_unavailable")
        print(json.dumps({"status": "blocked", "reason": code,
                          "executed": False, "release_authorized": False}))
        return 2

    receipt = sources.receipt()
    if not args.execute:
        print(json.dumps({"status": "source_verified_dry_run",
                          "source": receipt, "executed": False,
                          "release_authorized": False}, sort_keys=True))
        return 0

    try:
        result = queue._rpc("factory_resume_specialist_infrastructure_once_v1", {
            "p_run_id": sources.run_id,
            "p_expected_candidate_sha": sources.candidate_sha,
            "p_expected_generation": sources.execution_generation,
            "p_verified_factory_sha": sources.factory_sha,
            "p_evidence_digest": sources.evidence_digest,
            "p_reason_code": args.reason_code,
        })
        if (not isinstance(result, dict)
            or result.get("release_authorized") is not False
            or result.get("run_id") != sources.run_id
            or result.get("requeued") is not True):
            raise SpecialistInfrastructureRecoveryBlocked("replay_receipt_not_confirmed")
        # Post-write readback proves the database now has recoverable jobs.
        latest = queue._get("factory_specialist_lane_jobs?select=role,status,attempt_count"
                            "&run_id=eq." + sources.run_id + "&limit=4")
        if (not isinstance(latest, list) or len(latest) != 3
            or {row.get("role") for row in latest} != {"qa","security","operations"}
            or any(row.get("status") not in {"queued","claimed","passed"}
                   or type(row.get("attempt_count")) is not int
                   or not 0 <= row["attempt_count"] <= 3 for row in latest)):
            raise SpecialistInfrastructureRecoveryBlocked("postwrite_lane_reconciliation_blocked")
    except (SpecialistInfrastructureRecoveryBlocked, RuntimeError, ValueError,
            OSError, TypeError, KeyError):
        print(json.dumps({"status": "verification_blocked", "executed": "unknown",
                          "reason": "recheck_control_plane_and_audit",
                          "release_authorized": False}))
        return 3

    print(json.dumps({"status": "original_review_requeued", "source": receipt,
                      "executed": True, "specialist_review_passed": False,
                      "e2e_certified": False, "release_authorized": False},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
