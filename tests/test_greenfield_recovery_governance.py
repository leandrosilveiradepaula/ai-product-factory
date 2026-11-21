"""Greenfield governance and owner-continuation admission, offline/fail-closed.

Regression based on a real Factory greenfield: AGENTS.md may be absent at
the exact source SHA, while a previous operator Restart cannot impersonate
the authenticated GitHub OWNER continuation.
"""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ai_product_factory.execution_worker import ImplementationArtifact
from ai_product_factory.implementation_producer import ModelImplementationProducer
from ai_product_factory.model_executor import ModelExecutor, ModelResult, ModelRole
from ai_product_factory.source_scope_admission import SourceScopeBlocked
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue
from ai_product_factory.work_unit_context import build_context_packet, enforce_write_scopes


def source(kind):
    return {
        "project_key": "generic-app", "repository": "owner/generic-app",
        "project_kind": kind, "agent_key": "development",
        "plan_task_key": "tenant-permissions", "wave": 2,
        "task": {
            "title": "Review scoped SQL permissions",
            "description": "Fix only the recorded security finding",
            "acceptance_criteria": ["No unscoped grants"],
        },
        "assignment": {
            "scope_keys": ["supabase/migrations/001_permissions.sql"],
            "required_capabilities": ["implementation"],
        },
        "constraints": ["No production merge", "No unapproved database migrations"],
    }


class Captured:
    def __init__(self):
        self.request = None

    def execute(self, request):
        self.request = request
        return ModelResult(
            ModelRole.PRIMARY,
            json.dumps({
                "plan_markdown": "No mutation in offline test",
                "files": [],
                "commit_message": "", "pr_title": "", "pr_body": "",
                "blocked_reason": "Synthetic offline test only",
                "decision_needed": None,
            }),
            provider_ref="offline",
        )


class GreenfieldGovernancePromptTests(unittest.TestCase):
    def make(self, kind, snapshot):
        packet = build_context_packet(
            source=source(kind), impact={}, base_commit="a" * 40,
            branch="factory/change-set-test", repository_snapshot=snapshot,
        )
        capture = Captured()
        item = SimpleNamespace(
            task_id="task", run_id="run", project_key="generic-app",
            repository="owner/generic-app", change_set_id="cs",
            context_packet=packet.payload,
        )
        ModelImplementationProducer(ModelExecutor(primary=capture)).produce(item)
        return packet, capture.request

    def test_greenfield_missing_agents_is_not_automatic_governance_block(self):
        packet, request = self.make("greenfield", {
            "README.md": "# Candidate in development; no production merge",
            "supabase/migrations/001_permissions.sql": "revoke all on schema public from public;",
        })
        ctx = json.loads(request.context)
        self.assertEqual(ctx["repository"]["project_kind"], "greenfield")
        self.assertNotIn("AGENTS.md", ctx["repository_snapshot"])
        self.assertEqual(
            ctx["repository"]["write_scopes"],
            ["supabase/migrations/001_permissions.sql"],
        )
        self.assertIn("AGENTS.md may legitimately be absent", request.objective)
        self.assertIn("do not invent its content or block solely", request.objective)
        self.assertIn("No production merge", json.dumps(ctx))
        with self.assertRaises(PermissionError):
            enforce_write_scopes(["AGENTS.md"], ctx["repository"]["write_scopes"])

    def test_provided_agents_remains_authoritative_at_exact_sha(self):
        packet, request = self.make("greenfield", {
            "AGENTS.md": "No destructive migrations; require human production gate.",
            "README.md": "# Product",
        })
        self.assertEqual(json.loads(request.context)["repository_snapshot"]["AGENTS.md"],
                         "No destructive migrations; require human production gate.")
        self.assertIn("AGENTS.md remains authoritative", request.objective)

    def test_existing_missing_governance_gets_no_greenfield_exemption(self):
        packet, request = self.make("existing", {"README.md": "# Product"})
        self.assertEqual(packet.payload["repository"]["project_kind"], "existing")
        self.assertIn("missing mandatory governance is never permission", request.objective)

    def test_unknown_kind_is_not_mistaken_for_greenfield(self):
        packet, _ = self.make("unverified", {})
        self.assertEqual(packet.payload["repository"]["project_kind"], "unspecified")

    def test_missing_owner_continuation_fails_before_github_read(self):
        q = SupabaseRuntimeQueue(
            url="https://example.supabase.co", service_role_key="not-a-real-key",
        )
        q._get = lambda path: [{
            "id": "project", "repository": "owner/generic-app",
            "project_kind": "greenfield",
            "manifest": {
                "source": "factory-console", "onboarding_mode": "greenfield",
                "bootstrap_request_id": "a" * 36,
            },
        }]
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter") as github:
            with self.assertRaises(SourceScopeBlocked) as exc:
                q._live_candidate_context("project", {})
        self.assertEqual(exc.exception.code, "greenfield_owner_continuation_required")
        github.assert_not_called()

    def test_unauthenticated_recovery_is_settled_with_typed_durable_reason(self):
        q = SupabaseRuntimeQueue(
            url="https://example.supabase.co", service_role_key="not-a-real-key",
        )
        events = []
        q._rpc = lambda name, data: (
            events.append((name, data)) or
            ({
                "run_id": "r", "task_id": "t", "project_id": "p",
                "project_key": "generic-app",
                "stages": ["reconciliation", "gap_analysis", "planning"],
                "context": {"manifest": {"source": "factory-console"}},
                "execution_generation": 1,
            } if name == "factory_claim_next_run" else None)
        )
        q._reconciliation_context = lambda project, context: context
        q._live_candidate_context = Mock(
            side_effect=SourceScopeBlocked("greenfield_owner_continuation_required"),
        )
        with self.assertRaises(SourceScopeBlocked):
            q.claim_next("worker")
        self.assertEqual([name for name, _ in events], [
            "factory_claim_next_run", "factory_assert_claimed_run_epoch",
            "factory_finish_run",
        ])
        self.assertEqual(events[-1][1]["p_error"],
                         "reconciliation_greenfield_owner_continuation_required")

    def test_arbitrary_reason_cannot_be_persisted_as_typed_source_code(self):
        with self.assertRaises(ValueError):
            SourceScopeBlocked("attacker_supplied_diagnostic")


if __name__ == "__main__":
    unittest.main()
