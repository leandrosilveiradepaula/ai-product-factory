#!/usr/bin/env python3
"""Audit a fresh, operator-started Factory run without writing or spending."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from ai_product_factory.autonomy_journey import STAGES
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Read-only exact-run Factory journey evidence")
    parser.add_argument("--project-key",required=True)
    parser.add_argument("--since-utc",required=True,
                        help="Reject every Start before this UTC instant")
    parser.add_argument("--run-id",
                        help="Optional specific UUID from the explicit human Start")
    parser.add_argument("--require-at-least",choices=("none",)+STAGES,default="none")
    args=parser.parse_args(argv)
    try:
        since=datetime.fromisoformat(args.since_utc.replace("Z","+00:00"))
        report=SupabaseJourneyReader().read(
            project_key=args.project_key,since=since,run_id=args.run_id,
        )
        result=report.as_json()
        result["required_stage"]=args.require_at_least
        passed=(report.status!="blocked" and
                (args.require_at_least=="none" or
                 any(item.name==args.require_at_least and item.status=="verified"
                     for item in report.stages)))
        result["requirement_met"]=passed
        print(json.dumps(result,sort_keys=True,ensure_ascii=False))
        return 0 if passed else 2
    except (ValueError,RuntimeError,PermissionError,KeyError,TypeError) as exc:
        # Do not print arbitrary downstream HTTP bodies, headers, prompts,
        # service credentials, user metadata or audit payloads.
        kind=type(exc).__name__
        print(json.dumps({
            "project_key":args.project_key,"status":"blocked",
            "required_stage":args.require_at_least,"requirement_met":False,
            "blocker":"unverifiable_live_evidence",
            "error_type":kind,"product_ready":False,
            "paid_calls":0,"writes":0,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    sys.exit(main())
