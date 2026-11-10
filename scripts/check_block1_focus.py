"""Fail-closed B1-B4 PR focus guard. Not a product readiness certifier.

Trust model:
* GitHub PR event and exact git diff identify the candidate.
* CI loads this script from the PR BASE commit on subsequent PRs, never from
  mutable candidate code (bootstrap is the one deliberate exception).
* PR text declares intent; it cannot grant runtime permissions or a merge.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
SHA = re.compile(r"[0-9a-f]{40}\Z")
INCIDENT = re.compile(r"https://github\.com/leandrosilveiradepaula/ai-product-factory/issues/[1-9][0-9]*\Z")
BLOCKS = frozenset({"B1", "B2", "B3", "B4"})
CRITERIA = {
    "B1": frozenset({"functional_completeness/requirements_inventory",
                     "documentation/setup_configuration", "documentation/operations"}),
    "B2": frozenset({"security/authn_authz", "security/data_access_boundaries",
                     "security/secrets_dependencies", "test_strategy/unit_integration",
                     "test_strategy/regression_gates",
                     "functional_completeness/mock_noop_demo_inventory"}),
    "B3": frozenset({"product_experience/surface_inventory",
                     "product_experience/responsive", "product_experience/accessibility",
                     "product_experience/states"}),
    "B4": frozenset({"test_strategy/critical_e2e",
                     "functional_completeness/critical_journeys",
                     "documentation/release_rollback", "observability_operations/health",
                     "observability_operations/traceability",
                     "observability_operations/recovery_alerting"}),
}
assert sum(map(len, CRITERIA.values())) == 19
ALL_CRITERIA = frozenset().union(*CRITERIA.values())
assert len(ALL_CRITERIA) == 19
META = re.compile(r"^Factory-([A-Za-z-]+):[ \t]*(.+?)[ \t]*$", re.MULTILINE)
REQUIRED = frozenset({"Block", "Criteria", "Intent", "Acceptance", "Scope", "Cross-Repo"})
ALLOWED = REQUIRED | {"Incident", "Human-Gates"}
PREFIXES = (".github/", ".factory/", "apps/", "docs/", "scripts/", "src/",
            "supabase/", "tests/")
ROOT_FILES = frozenset({"AGENTS.md", "MEMORY.md", "PROJECT_PLAN.md", "README.md",
                        "pyproject.toml", ".env.example", "requirements.txt",
                        "requirements-dev.txt", "package.json", "package-lock.json"})
SENSITIVE = ("supabase/migrations/", "supabase/functions/",
             "apps/console/", ".github/workflows/")


class FocusDenied(ValueError):
    pass


def _fields(body: object) -> dict[str, str]:
    if not isinstance(body, str) or not 1 <= len(body) <= 60000:
        raise FocusDenied("pr_body_unavailable")
    fields: dict[str, str] = {}
    for key, value in META.findall(body):
        if key not in ALLOWED or key in fields:
            raise FocusDenied("duplicate_or_unknown_focus_field")
        fields[key] = value.strip()
    if not REQUIRED.issubset(fields):
        raise FocusDenied("focus_fields_missing")
    return fields


def _list(value: str) -> set[str]:
    parts = [x.strip() for x in value.split(",")]
    if any(not x for x in parts) or len(parts) != len(set(parts)):
        raise FocusDenied("duplicate_or_empty_focus_list")
    return set(parts)


def verify(event: object, repository: str, base: str, head: str,
           files: list[str]) -> dict:
    if repository != REPOSITORY:
        raise FocusDenied("non_factory_repository")
    if not isinstance(base, str) or not isinstance(head, str) or (
        not SHA.fullmatch(base) or not SHA.fullmatch(head) or base == head
    ):
        raise FocusDenied("sha_identity_invalid")
    if not isinstance(event, dict) or event.get("action") not in {
        "opened", "synchronize", "reopened", "edited", "ready_for_review"
    }:
        raise FocusDenied("pr_event_invalid")
    pr = event.get("pull_request")
    if not isinstance(pr, dict) or type(pr.get("number")) is not int or pr["number"] <= 0:
        raise FocusDenied("pr_identity_invalid")
    origin = pr.get("head") or {}
    target = pr.get("base") or {}
    if (not isinstance(origin, dict) or not isinstance(target, dict)
        or origin.get("sha") != head
        or (origin.get("repo") or {}).get("full_name") != REPOSITORY
        or target.get("sha") != base
        or target.get("ref") != "main"
        or (target.get("repo") or {}).get("full_name") != REPOSITORY):
        raise FocusDenied("pr_commit_origin_or_base_invalid")
    if (not isinstance(files, list) or not 1 <= len(files) <= 3000
        or len(files) != len(set(files))):
        raise FocusDenied("diff_inventory_invalid")
    for file in files:
        if (not isinstance(file, str) or not 1 <= len(file) <= 450
            or file.startswith("/") or "\\" in file or ".." in Path(file).parts
            or any(ord(c) < 32 or ord(c) == 127 for c in file)
            or (file not in ROOT_FILES and not file.startswith(PREFIXES))):
            raise FocusDenied("file_outside_factory_scope")
    fields = _fields(pr.get("body"))
    blocks, criteria = _list(fields["Block"]), _list(fields["Criteria"])
    if (not blocks or not blocks.issubset(BLOCKS) or not criteria
        or not criteria.issubset(ALL_CRITERIA)
        or any(not any(c in CRITERIA[b] for b in blocks) for c in criteria)):
        raise FocusDenied("criterion_not_mapped_to_block")
    if (fields["Scope"] != REPOSITORY or fields["Cross-Repo"] != "read-only"):
        raise FocusDenied("cross_repo_write_or_unbounded_scope")
    acceptance = fields["Acceptance"].lower()
    if (not 30 <= len(acceptance) <= 1600
        or "supabase" not in acceptance or "sha" not in acceptance):
        raise FocusDenied("no_independent_exact_sha_acceptance")
    if fields["Intent"] == "advance":
        if not any(file.startswith(("scripts/", "src/", "tests/", "apps/",
                                   "supabase/", ".github/")) for file in files):
            raise FocusDenied("documentation_only_advance")
    elif fields["Intent"] == "repair-regression":
        if not INCIDENT.fullmatch(fields.get("Incident", "")):
            raise FocusDenied("missing_factory_regression_incident")
    else:
        raise FocusDenied("invalid_focus_intent")
    if any(file.startswith(SENSITIVE) for file in files):
        if "human-review" not in fields.get("Human-Gates", ""):
            raise FocusDenied("protected_path_without_human_gate_declaration")
    return {
        "schema": "factory-b1-b4-focus-gate-v1",
        "pr": pr["number"],
        "base_sha": base,
        "head_sha": head,
        "criteria": sorted(criteria),
        "blocks": sorted(blocks),
        "changed_files": len(files),
        "scope_guard_passed": True,
        "certification_pass_claimed": False,
        "production_release_authorized": False,
        "cross_repo_writes_authorized": False,
    }


def exact_diff(root: Path, base: str, head: str) -> list[str]:
    try:
        current = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True,
                                 timeout=15).stdout.strip()
        if current != head:
            raise FocusDenied("checkout_not_exact_pr_head")
        result = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", "-z",
             "--diff-filter=ACDMRTUXB", base + "..." + head],
            capture_output=True, check=True, timeout=20)
        return [path.decode("utf-8", "strict") for path in result.stdout.split(b"\0") if path]
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise FocusDenied("git_diff_unavailable") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--worktree", required=True, type=Path)
    args = parser.parse_args()
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        receipt = verify(event, args.repository, args.base, args.head,
                         exact_diff(args.worktree, args.base, args.head))
    except (FocusDenied, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": str(exc) if isinstance(exc, FocusDenied) else "unverified",
                          "certification_pass_claimed": False}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
