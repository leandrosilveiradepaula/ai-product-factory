"""Create/recover one independent durable product-readiness certification."""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from ai_product_factory.product_readiness_certification import certify_product_readiness, CertificationEvidenceError
from ai_product_factory.supabase_delivery_store import SupabaseDeliveryStore


def _github_get(token: str):
    def get(path: str):
        request = urllib.request.Request("https://api.github.com" + path,
            headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                     "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    return get



def require_verified_baseline(value: object, *, repository: str, assessed_commit: str) -> dict:
    """Accept only a same-repository, same-SHA conservative CI evidence envelope.

    The whole envelope is revalidated after the certifier independently fetches
    live GitHub HEAD, exact push validation run and two successful CI jobs.
    Never trust a file alone to confer product readiness.
    """
    if not isinstance(value, dict):
        raise CertificationEvidenceError("verified baseline must be a JSON object")
    if (value.get("schema_version") != 1
            or value.get("scope") != "read_only_independent_source_verified_baseline"
            or value.get("repository") != repository
            or value.get("assessed_commit") != assessed_commit
            or value.get("writes") != 0 or value.get("paid_calls") != 0
            or value.get("start_authorized") is not False
            or value.get("product_ready") is not False
            or not isinstance(value.get("manifest"), dict)
            or not isinstance(value.get("source_snapshot"), dict)
            or not isinstance(value.get("evidence_digest"), str)
            or not isinstance(value.get("assessment"), dict)):
        raise CertificationEvidenceError("untrusted or inconsistent readiness baseline")
    return value["manifest"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent deterministic product-readiness certification")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assessed-commit", required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--require-verified-baseline", action="store_true",
                        help="only accept the independently verified conservative CI envelope")
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required for exact-SHA GitHub evidence")
    evidence = json.loads(args.evidence_file.read_text(encoding="utf-8"))
    manifest = (require_verified_baseline(
        evidence, repository=args.repository, assessed_commit=args.assessed_commit
    ) if args.require_verified_baseline else evidence)
    certification = certify_product_readiness(repository=args.repository, assessed_commit=args.assessed_commit,
                                               manifest=manifest, github_get=_github_get(token))
    if args.require_verified_baseline:
        if (certification.report["source_snapshot"] != evidence["source_snapshot"]
                or certification.evidence_digest != evidence["evidence_digest"]
                or certification.assessment.as_result() != evidence["assessment"]
                or certification.assessment.ready
                or certification.assessment.status != "not_ready"):
            raise CertificationEvidenceError("readiness evidence changed before persistence")
    store = SupabaseDeliveryStore()
    begun = store.begin_product_readiness_certification(project_key=args.project_key,
        repository=args.repository, assessed_commit=args.assessed_commit,
        evidence_digest=certification.evidence_digest)
    saved = store.persist_product_readiness_certification(certification_id=begun["certification_id"],
        run_id=begun["run_id"], assessment=certification.assessment, report=certification.report,
        evidence_digest=certification.evidence_digest)
    print(json.dumps({"certification": begun, "evaluation": saved,
                      "product_ready": certification.assessment.ready,
                      "status": certification.assessment.status}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
