"""Create/recover one independent durable product-readiness certification."""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from ai_product_factory.product_readiness_certification import certify_product_readiness
from ai_product_factory.supabase_delivery_store import SupabaseDeliveryStore


def _github_get(token: str):
    def get(path: str):
        request = urllib.request.Request("https://api.github.com" + path,
            headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                     "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    return get


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent deterministic product-readiness certification")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assessed-commit", required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required for exact-SHA GitHub evidence")
    manifest = json.loads(args.evidence_file.read_text(encoding="utf-8"))
    certification = certify_product_readiness(repository=args.repository, assessed_commit=args.assessed_commit,
                                               manifest=manifest, github_get=_github_get(token))
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
