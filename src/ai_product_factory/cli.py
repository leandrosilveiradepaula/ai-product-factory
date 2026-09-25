from __future__ import annotations

import argparse
import json

from .codex_policy import classify_codex_need
from .manifest import load_manifest
from .model_executor import ModelRequest
from .models import Complexity, TaskProfile
from .openai_provider import OpenAIResponsesProvider


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-product-factory")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a project manifest")
    validate.add_argument("manifest")

    codex = sub.add_parser("codex-decision", help="classify whether Codex should be used")
    codex.add_argument("--complexity", choices=[c.value for c in Complexity], default="low")
    codex.add_argument("--files", type=int, default=1)
    codex.add_argument("--deep-debug", action="store_true")
    codex.add_argument("--large-refactor", action="store_true")
    codex.add_argument("--broad-repo-investigation", action="store_true")
    codex.add_argument("--direct-tools-insufficient", action="store_true")
    codex.add_argument("--mechanical-change", action="store_true")

    execute = sub.add_parser("openai-execute", help="execute one primary-model request")
    execute.add_argument("--task-id", required=True)
    execute.add_argument("--objective", required=True)
    execute.add_argument("--context", default="")
    execute.add_argument("--complexity", choices=[c.value for c in Complexity], default="medium")
    execute.add_argument("--reasoning-effort", default="medium")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    if args.command == "validate":
        data = load_manifest(args.manifest)
        print(json.dumps({"valid": True, "project": data["project"]["key"]}))
        return 0

    if args.command == "codex-decision":
        decision = classify_codex_need(
            TaskProfile(
                complexity=Complexity(args.complexity),
                estimated_files=args.files,
                deep_debug=args.deep_debug,
                large_refactor=args.large_refactor,
                broad_repo_investigation=args.broad_repo_investigation,
                direct_tools_sufficient=not args.direct_tools_insufficient,
                repetitive_mechanical_change=args.mechanical_change,
            )
        )
        print(json.dumps({
            "level": decision.level,
            "should_use": decision.should_use,
            "reasons": decision.reasons,
        }, ensure_ascii=False))
        return 0

    if args.command == "openai-execute":
        provider = OpenAIResponsesProvider()
        result = provider.execute_for_complexity(
            ModelRequest(
                task_id=args.task_id,
                objective=args.objective,
                context=args.context,
            ),
            Complexity(args.complexity),
            reasoning_effort=args.reasoning_effort,
        )
        print(json.dumps({
            "role": result.role.value,
            "provider_ref": result.provider_ref,
            "usage": result.usage or {},
            "output": result.output,
        }, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
