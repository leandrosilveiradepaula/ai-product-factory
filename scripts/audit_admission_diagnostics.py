#!/usr/bin/env python3
"""Issue-triggerable bounded Control Plane admission diagnostic; no model or writes."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from ai_product_factory.admission_diagnostics import SupabaseAdmissionReader


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Control Plane admission read-only evidence")
    parser.add_argument("--project-key",required=True)
    parser.add_argument("--run-id")
    args=parser.parse_args(argv)
    try:
        report=SupabaseAdmissionReader().read(project_key=args.project_key,run_id=args.run_id)
        # These flags describe the command itself; they never authorize runtime claims.
        report.update({"evidence_state":"observed","paid_calls":0,"writes":0,
                       "product_ready":False})
        sha=os.getenv("GITHUB_SHA","")
        if re.fullmatch(r"[a-f0-9]{40}",sha,re.ASCII):
            report["source_sha"]=sha
        print(json.dumps(report,ensure_ascii=False,sort_keys=True))
        return 0
    except Exception as exc:
        # Never print raw HTTP errors, Control Plane payloads, prompts, or secrets.
        project=args.project_key if isinstance(args.project_key,str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}",args.project_key,re.ASCII) else None
        run=args.run_id if isinstance(args.run_id,str) and re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",args.run_id,re.ASCII) else None
        report={"project_key":project,"run_id":run,"status":"blocked",
                "reason_code":"unverifiable_live_evidence","next_step":"investigate_read_failure",
                "error_type":type(exc).__name__,"evidence_state":"insufficient_evidence",
                "read_only":True,"paid_calls":0,"writes":0,"product_ready":False}
        print(json.dumps(report,sort_keys=True))
        return 2


if __name__=="__main__":
    sys.exit(main())
