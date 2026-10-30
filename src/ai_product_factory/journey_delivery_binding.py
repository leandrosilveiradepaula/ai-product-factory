"""Journey Delivery Binding v2: immutable identity across delivery stages.

This module deliberately validates a *binding*, rather than a project-wide
cursor.  A SHA describes bytes; it cannot authorize a new request or select a
Preview destination by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping
from uuid import UUID


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_REF = re.compile(r"(?:main|preview/[A-Za-z0-9][A-Za-z0-9/_-]{0,100}|factory/journey-[0-9a-f-]{36})\Z")
_STATES = frozenset({"intake_accepted", "awaiting_source", "source_bound", "executing", "preview_verified", "awaiting_release", "released_observed", "closed"})


class JourneyBindingBlocked(PermissionError):
    """A fixed safe reason; callers must not persist provider text."""


def canonical_digest(value: Mapping[str, object]) -> str:
    """Stable digest used for idempotency/provenance, never authentication."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class JourneyBinding:
    journey_id: str
    project_id: str
    request_id: str
    execution_generation: int
    policy_version: int
    policy_digest: str
    repository: str
    source_commit: str
    source_ref: str
    source_mode: str
    integration_branch: str
    preview_branch_prefix: str
    preview_base_ref: str
    release_base_ref: str
    binding_version: int

    @classmethod
    def parse(cls, value: object, *, project_id: str, request_id: str, repository: str) -> "JourneyBinding":
        if not isinstance(value, dict):
            raise JourneyBindingBlocked("journey_binding_missing")
        required = ("journey_id", "project_id", "request_id", "execution_generation", "policy_version", "policy_digest", "repository", "source_commit", "source_ref", "source_mode", "integration_branch", "preview_base_ref", "release_base_ref", "binding_version")
        if any(key not in value for key in required):
            raise JourneyBindingBlocked("journey_binding_incomplete")
        try:
            journey_id = str(UUID(str(value["journey_id"])))
        except (ValueError, TypeError, AttributeError) as exc:
            raise JourneyBindingBlocked("journey_binding_identity_invalid") from exc
        if value["project_id"] != project_id or value["request_id"] != request_id:
            raise JourneyBindingBlocked("journey_binding_cross_request")
        generation = value["execution_generation"]
        version = value["policy_version"]
        binding_version = value["binding_version"]
        if (type(generation) is not int or generation < 1 or type(version) is not int or version < 1
                or type(binding_version) is not int or binding_version != 2):
            raise JourneyBindingBlocked("journey_binding_version_invalid")
        if value["repository"] != repository or not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
            raise JourneyBindingBlocked("journey_binding_repository_invalid")
        if not isinstance(value["source_commit"], str) or not _SHA.fullmatch(value["source_commit"]):
            raise JourneyBindingBlocked("journey_binding_source_invalid")
        if value["source_mode"] not in {"main_snapshot", "authorized_preview", "greenfield_bootstrap"}:
            raise JourneyBindingBlocked("journey_binding_source_mode_invalid")
        # A V2 implementation may be Preview-only, but the release destination
        # is always the protected main branch and is never inferred from it.
        if value["release_base_ref"] != "main":
            raise JourneyBindingBlocked("journey_release_destination_not_main")
        for key in ("source_ref", "preview_base_ref", "release_base_ref"):
            ref = value[key]
            if not isinstance(ref, str) or not _REF.fullmatch(ref) or ".." in ref or "//" in ref:
                raise JourneyBindingBlocked("journey_binding_ref_invalid")
        branch = value["integration_branch"]
        if (not isinstance(branch, str) or not _REF.fullmatch(branch)
                or not branch.startswith("factory/journey-" + journey_id)):
            raise JourneyBindingBlocked("journey_binding_destination_invalid")
        preview_prefix = value.get("preview_branch_prefix", "preview/journey-" + journey_id[:8])
        if (not isinstance(preview_prefix, str) or not re.fullmatch(r"preview/journey-[a-z0-9][a-z0-9/_-]{0,50}", preview_prefix)
                or ".." in preview_prefix or "//" in preview_prefix):
            raise JourneyBindingBlocked("journey_binding_preview_destination_invalid")
        digest = value["policy_digest"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise JourneyBindingBlocked("journey_binding_policy_invalid")
        return cls(journey_id, project_id, request_id, generation, version, digest, repository,
                   value["source_commit"], value["source_ref"], value["source_mode"], branch, preview_prefix,
                   value["preview_base_ref"], value["release_base_ref"], binding_version)

    def implementation_pr_base_ref(self) -> str:
        """Choose the PR base from the *same* immutable V2 Preview policy.

        Preview-only projects must not accidentally create main-target PRs;
        main-target projects use a separate journey-scoped Preview ref.
        """
        if self.preview_base_ref == "main" and self.release_base_ref == "main":
            return "main"
        if self.preview_base_ref.startswith("preview/") and self.release_base_ref == "main":
            return self.preview_base_ref
        raise JourneyBindingBlocked("journey_delivery_route_unsupported")

    def as_context(self) -> dict[str, object]:
        return {
            "journey_id": self.journey_id, "project_id": self.project_id,
            "request_id": self.request_id, "execution_generation": self.execution_generation,
            "policy_version": self.policy_version, "policy_digest": self.policy_digest,
            "repository": self.repository, "source_commit": self.source_commit,
            "source_ref": self.source_ref, "source_mode": self.source_mode,
            "integration_branch": self.integration_branch, "preview_branch_prefix": self.preview_branch_prefix, "preview_base_ref": self.preview_base_ref,
            "release_base_ref": self.release_base_ref, "binding_version": self.binding_version,
        }


def assert_preview_belongs_to_journey(item: object, policy: object) -> None:
    """Reject the legacy manifest's implicit Preview base for a V2 item."""
    raw = getattr(item, "journey_binding", None)
    if raw is None:
        return  # Legacy is deliberately isolated behind the rollout flag.
    binding = JourneyBinding.parse(raw, project_id=getattr(item, "project_id", ""),
                                  request_id=getattr(item, "request_id", ""),
                                  repository=getattr(item, "repository", ""))
    if getattr(policy, "base_ref", None) != binding.preview_base_ref:
        raise JourneyBindingBlocked("journey_preview_destination_mismatch")


def build_main_snapshot_binding(*, journey_id: str, project_id: str, request_id: str,
                                repository: str, generation: int, policy: Mapping[str, object],
                                main_sha: str) -> dict[str, object]:
    """Build the only automatic source mode allowed by V2: policy-approved main.

    The caller must obtain ``main_sha`` from GitHub immediately before the SQL
    CAS and recheck it at the external write boundary. A DRAFT/documentation PR
    is neither required nor accepted as a substitute for this policy.
    """
    if not isinstance(policy, Mapping) or policy.get("enabled") is not True:
        raise JourneyBindingBlocked("journey_policy_not_enabled")
    if policy.get("source_mode") != "main_snapshot":
        raise JourneyBindingBlocked("journey_source_mode_not_authorized")
    version = policy.get("version")
    digest = policy.get("digest")
    preview = policy.get("preview_base_ref")
    release = policy.get("release_base_ref")
    if (type(version) is not int or version < 1 or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(preview, str)
            or not isinstance(release, str) or not _SHA.fullmatch(main_sha)):
        raise JourneyBindingBlocked("journey_policy_invalid")
    raw = {"journey_id": journey_id, "project_id": project_id, "request_id": request_id,
           "execution_generation": generation, "policy_version": version, "policy_digest": digest,
           "repository": repository, "source_repository": repository, "source_commit": main_sha,
           "source_ref": "main", "source_mode": "main_snapshot",
           "integration_branch": "factory/journey-" + journey_id,
           "preview_branch_prefix": "preview/journey-" + journey_id[:8],
           "preview_base_ref": preview, "release_base_ref": release, "binding_version": 2}
    raw["source_proof_digest"] = canonical_digest({"repository": repository, "ref": "main", "sha": main_sha,
                                                     "policy_digest": digest, "request_id": request_id})
    return JourneyBinding.parse(raw, project_id=project_id, request_id=request_id, repository=repository).as_context() | {"source_repository": repository, "source_proof_digest": raw["source_proof_digest"]}


def resolve_pending_main_snapshot(*, journey: Mapping[str, object], project: Mapping[str, object],
                                  control: Mapping[str, object], github: object) -> dict[str, object]:
    """Deterministically resolve one persisted awaiting_source journey.

    This is intentionally the only automatic resolver: an explicit immutable
    project policy must authorize ``main_snapshot``. It never derives scope or
    authority from a PR body, request text, or the legacy delivery target.
    """
    if journey.get("state") not in {"intake_accepted", "awaiting_source"}:
        raise JourneyBindingBlocked("journey_not_awaiting_source")
    project_id, journey_id, request_id = project.get("id"), journey.get("id"), journey.get("request_id")
    repository = project.get("repository")
    policy = project.get("manifest", {}).get("journey_delivery_binding_v2") if isinstance(project.get("manifest"), dict) else None
    if not all(isinstance(x, str) and x for x in (project_id, journey_id, request_id, repository)):
        raise JourneyBindingBlocked("journey_source_identity_missing")
    if type(control.get("generation")) is not int or control.get("state") != "running":
        raise JourneyBindingBlocked("journey_execution_epoch_revoked")
    if getattr(github, "repository", None) != repository:
        raise JourneyBindingBlocked("journey_source_repository_unavailable")
    main_sha = github.get_branch_sha("main")
    binding = build_main_snapshot_binding(journey_id=journey_id, project_id=project_id,
        request_id=request_id, repository=repository, generation=control["generation"],
        policy=policy if isinstance(policy, Mapping) else {}, main_sha=main_sha)
    # A second read closes the unavoidable external-read/SQL-CAS window.
    if github.get_branch_sha("main") != main_sha:
        raise JourneyBindingBlocked("journey_source_ref_changed")
    return binding
