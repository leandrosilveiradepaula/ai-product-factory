"""B3 state PASS must be earned from multiple real immutable sources, not fixtures."""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

from ai_product_factory.independent_console_states_evidence import (
    REPO, REVIEWED_SOURCE_SHA, EXECUTED_STATE_FILES, REQUIRED_CI_STEPS,
    ConsoleStatesEvidenceBlocked, verify_console_states,
)
from ai_product_factory.independent_complete_console_evidence import VerifiedConsoleSurface
from ai_product_factory.independent_console_accessibility_evidence import VerifiedConsoleAccessibility
from ai_product_factory.independent_live_console_boundary_evidence import VerifiedLiveConsoleBoundaries
from ai_product_factory.independent_b2_signed_security_evidence import VerifiedSignedB2

SOURCE = "b" * 40
CURRENT = "c" * 40
VISUAL = 42
CONSOLE_CI = 99
ROOT = "/repos/" + REPO


def fixture():
    data = {}
    for sha in {SOURCE, CURRENT, REVIEWED_SOURCE_SHA}:
        data[ROOT + "/git/commits/" + sha] = {"tree": {"sha": sha}}
        data[ROOT + "/git/trees/" + sha + "?recursive=1"] = {
            "truncated": False,
            "tree": [
                {"path": path, "type": "blob", "mode": "100644", "sha": "d" * 40}
                for path in EXECUTED_STATE_FILES
            ],
        }
    data[ROOT + "/actions/runs?head_sha=" + SOURCE
         + "&event=push&per_page=100"] = {
        "total_count": 1,
        "workflow_runs": [{
            "id": CONSOLE_CI, "name": "Console validation",
            "path": ".github/workflows/console.yml", "event": "push",
            "head_sha": SOURCE, "head_branch": "main",
            "status": "completed", "conclusion": "success", "run_attempt": 1,
        }],
    }
    data[ROOT + "/actions/runs/" + str(CONSOLE_CI) + "/jobs?per_page=100"] = {
        "total_count": 1,
        "jobs": [{
            "name": "validate", "run_id": CONSOLE_CI, "head_sha": SOURCE,
            "status": "completed", "conclusion": "success",
            "steps": [{
                "name": name, "status": "completed", "conclusion": "success",
            } for name in REQUIRED_CI_STEPS],
        }],
    }
    gates = [
        {"status": status, "requested_at": "2026-10-01T10:00:00+00:00",
         "resolved_at": "2026-10-01T10:10:00+00:00"}
        for status in ("approved", "rejected")
    ]
    return data, gates


def proofs():
    return {
        "surface": VerifiedConsoleSurface(
            repository=REPO, assessed_commit=CURRENT, run_id=VISUAL,
            target_commit=SOURCE, artifact_id=20, source_commit=SOURCE),
        "accessibility": VerifiedConsoleAccessibility(
            repository=REPO, assessed_commit=CURRENT,
            run_id=VISUAL, artifact_id=21),
        "live_boundaries": VerifiedLiveConsoleBoundaries(
            repository=REPO, assessed_commit=CURRENT, run_id=VISUAL,
            b2_artifact_id=22, b3_artifact_id=23, b3_live_artifact_id=24),
        "signed_b2": VerifiedSignedB2(
            repository=REPO, assessed_commit=CURRENT,
            run_id=VISUAL, artifact_id=25,
            role_boundary_artifact_id=26, isolated_pg_run_id=27),
    }


class ConsoleStatesTests(unittest.TestCase):
    def verify(self, data=None, gates=None, proof=None):
        if data is None or gates is None:
            data, gates = fixture()
        if proof is None:
            proof = proofs()
        reads = []
        def github(path):
            reads.append(path)
            return copy.deepcopy(data[path])
        def control_plane(route):
            self.assertEqual(
                route, "factory_human_gates?select=status,requested_at,resolved_at"
                       "&order=requested_at.desc&limit=75")
            reads.append(route)
            return copy.deepcopy(gates)
        result = verify_console_states(
            repository=REPO, assessed_commit=CURRENT,
            github_get=github, control_plane_get=control_plane, **proof)
        self.assertTrue(all(path.startswith(ROOT + "/") or
                            path.startswith("factory_human_gates?select=")
                            for path in reads))
        return result

    def test_composite_real_and_isolated_state_proof(self):
        proof = self.verify()
        self.assertEqual(proof.criterion().criterion, "states")
        self.assertEqual(proof.criterion().verification_state, "observed")
        self.assertEqual(proof.approved_transitions, 1)
        self.assertEqual(proof.rejected_transitions, 1)
        r = proof.receipt()
        self.assertEqual(r["production_writes"], 0)
        self.assertEqual(r["paid_calls"], 0)
        self.assertFalse(r["critical_e2e_certified"])
        self.assertFalse(r["critical_journeys_certified"])
        self.assertTrue(r["offline_fault_injection_not_production_state"])
        self.assertNotIn("2026-10-01", str(r))
        self.assertIn(CURRENT, proof.criterion().evidence[0])
        self.assertIn(CURRENT, proof.criterion().evidence[1])

    def test_missing_actual_backend_or_chromium_is_not_pass(self):
        for mutation in (
            lambda p: p["live_boundaries"].__class__(
                **{**p["live_boundaries"].__dict__, "b3_live_artifact_id": None}),
            lambda p: p["live_boundaries"].__class__(
                **{**p["live_boundaries"].__dict__, "b3_artifact_id": None}),
            lambda p: p["accessibility"].__class__(
                **{**p["accessibility"].__dict__, "artifact_id": 0}),
            lambda p: p["signed_b2"].__class__(
                **{**p["signed_b2"].__dict__, "run_id": 777}),
        ):
            p = proofs()
            names = ("live_boundaries", "live_boundaries", "accessibility", "signed_b2")
            # Find exactly one replaced dataclass by identity, no mutation of
            # a trusted proof object from caller-supplied JSON.
            target = mutation(p)
            key = next(k for k in names if isinstance(target, type(p[k])))
            p[key] = target
            with self.assertRaises(ConsoleStatesEvidenceBlocked):
                self.verify(proof=p)

    def test_source_script_tampering_and_truncation_fail(self):
        for mutation in (
            lambda d: d[ROOT + "/git/trees/" + CURRENT + "?recursive=1"][
                "tree"][0].update(sha="0" * 40),
            lambda d: d[ROOT + "/git/trees/" + REVIEWED_SOURCE_SHA
                       + "?recursive=1"].update(truncated=True),
            lambda d: d[ROOT + "/git/trees/" + SOURCE + "?recursive=1"][
                "tree"].pop(),
        ):
            d, gates = fixture()
            mutation(d)
            with self.assertRaises(ConsoleStatesEvidenceBlocked):
                self.verify(d, gates)

    def test_fake_ci_identity_or_skipped_real_next_state_test_fails(self):
        for mutation in (
            lambda d: d[ROOT + "/actions/runs?head_sha=" + SOURCE
                       + "&event=push&per_page=100"]["workflow_runs"][0].update(
                           head_sha=CURRENT),
            lambda d: d[ROOT + "/actions/runs/" + str(CONSOLE_CI)
                       + "/jobs?per_page=100"]["jobs"][0]["steps"][-1].update(
                           conclusion="skipped"),
            lambda d: d[ROOT + "/actions/runs/" + str(CONSOLE_CI)
                       + "/jobs?per_page=100"]["jobs"][0].update(
                           conclusion="failure"),
        ):
            d, gates = fixture()
            mutation(d)
            with self.assertRaises(ConsoleStatesEvidenceBlocked):
                self.verify(d, gates)

    def test_missing_or_malformed_real_gate_outcomes_fail(self):
        for gates in (
            [{"status": "approved", "requested_at": "2026-10-01T10:00:00+00:00",
              "resolved_at": "2026-10-01T10:10:00+00:00"}],
            [{"status": "approved", "requested_at": "2026-10-01T10:00:00+00:00",
              "resolved_at": "2026-10-01T10:10:00+00:00"},
             {"status": "rejected", "requested_at": "2026-10-01T10:20:00+00:00",
              "resolved_at": "2026-10-01T10:10:00+00:00"}],
            [{"status": "approved", "requested_at": "2026-10-01T10:00:00+00:00",
              "resolved_at": "2026-10-01T10:10:00+00:00"},
             {"status": "rejected", "requested_at": "2026-10-01T10:00:00+00:00",
              "resolved_at": None}],
        ):
            d, _ = fixture()
            with self.assertRaises(ConsoleStatesEvidenceBlocked):
                self.verify(d, gates)

    def test_production_and_certificate_wiring_is_fail_closed(self):
        root = Path(__file__).resolve().parents[1]
        builder = (root / "scripts/build_readiness_evidence_manifest.py").read_text()
        certifier = (root / "scripts/certify_product_readiness.py").read_text()
        workflow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        self.assertIn("states_proof = verify_console_states_fn(", builder)
        self.assertIn("states_proof = verify_console_states(", certifier)
        self.assertIn('evidence.get("independent_console_states_evidence")', certifier)
        self.assertEqual(workflow.count("--verify-independent-console-states"), 2)


if __name__ == "__main__":
    unittest.main()
