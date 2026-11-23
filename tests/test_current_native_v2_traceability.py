from __future__ import annotations

import unittest

from ai_product_factory.current_native_v2_traceability import (
    CurrentTraceabilityBlocked, REPO, verify_current_crm_v2_traceability,
)

SHA = "a" * 40


def env():
    return {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_NAME": "workflow_run", "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": REPO + "/.github/workflows/autonomous-runner.yml@refs/heads/main",
        "GITHUB_RUN_ID": "123",
    }


def github(path):
    if path.endswith("/actions/runs/123"):
        return {"id": 123, "name": "Factory autonomous runner",
                "path": ".github/workflows/autonomous-runner.yml", "event": "workflow_run",
                "head_branch": "main", "head_sha": SHA, "run_attempt": 1}
    if path.endswith("/git/ref/heads/main"):
        return {"object": {"sha": SHA}}
    raise AssertionError(path)


def receipt(**overrides):
    value = {"schema_version": 1, "project_key": "crm-infodive",
             "journey_id": "bb14e150-2c7e-423b-8e5d-e211dab6225c",
             "requirement_met": True, "status": "integrated_nonproduction",
             "production_released": False, "product_ready": False,
             "paid_calls": 0, "writes": 0}
    value.update(overrides)
    return value


class CurrentNativeV2TraceabilityTests(unittest.TestCase):
    def test_current_trusted_runner_and_readonly_audit_produce_one_scoped_claim(self):
        proof = verify_current_crm_v2_traceability(
            repository=REPO, assessed_commit=SHA, github_get=github,
            reader=object(), environment=env(), audit=lambda **_: receipt(),
        )
        self.assertEqual((proof.domain, proof.criterion),
                         ("observability_operations", "traceability"))
        self.assertEqual(proof.verification_state, "observed")
        self.assertIn(SHA, proof.evidence[0])

    def test_wrong_identity_and_any_release_claim_fail_closed(self):
        bad = env(); bad["GITHUB_EVENT_NAME"] = "workflow_dispatch"
        with self.assertRaises(CurrentTraceabilityBlocked):
            verify_current_crm_v2_traceability(
                repository=REPO, assessed_commit=SHA, github_get=github,
                reader=object(), environment=bad, audit=lambda **_: receipt(),
            )
        for changed in ({"production_released": True}, {"writes": 1},
                        {"status": "released"}, {"requirement_met": False}):
            with self.subTest(changed=changed), self.assertRaises(CurrentTraceabilityBlocked):
                verify_current_crm_v2_traceability(
                    repository=REPO, assessed_commit=SHA, github_get=github,
                    reader=object(), environment=env(), audit=lambda **_: receipt(**changed),
                )


if __name__ == "__main__":
    unittest.main()
