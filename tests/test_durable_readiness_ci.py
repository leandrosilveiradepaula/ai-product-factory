"""The post-CI readiness writer must only persist conservative exact-SHA evidence."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import certify_product_readiness as cli
from build_readiness_evidence_manifest import build_verified_baseline
from ai_product_factory.product_readiness_certification import CertificationEvidenceError, VerifiedCriterionEvidence
from tests.test_product_readiness_certification import REPO, SHA, github


class DurableReadinessCITests(unittest.TestCase):
    def baseline(self):
        data = github()
        return build_verified_baseline(
            repository=REPO, sha=SHA, github_get=lambda path: data[path]
        )

    def run_cli(self, envelope, *, sha=SHA, verify_native_v2=False, verify_health=False,
                persist_error=None):
        data = github()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            with patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only-token"}):
                with patch.object(cli, "_github_get",
                                  return_value=lambda route: data[route]):
                    with patch.object(cli, "SupabaseDeliveryStore") as cls:
                        store = cls.return_value
                        store.begin_product_readiness_certification.return_value = {
                            "certification_id": "cert-fixture",
                            "run_id": "run-fixture",
                            "assessed_commit": SHA,
                        }
                        if persist_error is None:
                            store.persist_product_readiness_certification.return_value = {
                                "run_id": "run-fixture",
                                "assessed_commit": SHA,
                                "evaluation_status": "failed",
                            }
                        else:
                            store.persist_product_readiness_certification.side_effect = persist_error
                        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                            argv = [
                                "--project-key", "ai-product-factory",
                                "--repository", REPO,
                                "--assessed-commit", sha,
                                "--evidence-file", str(path),
                                "--require-verified-baseline",
                                *(['--verify-native-v2-traceability'] if verify_native_v2 else []),
                                *(['--verify-independent-health'] if verify_health else []),
                            ]
                            if persist_error is None:
                                result = cli.main(argv)
                                raised = None
                            else:
                                with self.assertRaises(RuntimeError) as failure:
                                    cli.main(argv)
                                result = None
                                raised = failure.exception
                        return result, cls, store, stdout.getvalue(), raised

    def test_current_sha_baseline_persists_only_not_ready(self):
        envelope = self.baseline()
        result, cls, store, output, _ = self.run_cli(envelope)
        self.assertEqual(result, 0)
        self.assertFalse(json.loads(output)["product_ready"])
        self.assertEqual(json.loads(output)["status"], "not_ready")
        self.assertEqual(store.begin_product_readiness_certification.call_count, 1)
        args = store.begin_product_readiness_certification.call_args.kwargs
        self.assertEqual(args["assessed_commit"], SHA)
        self.assertEqual(args["repository"], REPO)
        self.assertEqual(args["evidence_digest"], envelope["evidence_digest"])
        persist = store.persist_product_readiness_certification.call_args.kwargs
        self.assertFalse(persist["assessment"].ready)
        self.assertEqual(persist["report"]["assessment"]["status"], "not_ready")
        self.assertEqual(
            persist["report"]["criteria"]["test_strategy"]["unit_integration"]["status"],
            "passed",
        )
        self.assertEqual(
            sum(row["status"] == "passed"
                for rows in persist["report"]["criteria"].values()
                for row in rows.values()), 1
        )
        self.assertNotIn("fixture-only-token", output)

    def test_sha_bound_v2_proof_can_attest_only_traceability(self):
        def proof(repository, assessed_commit, **_):
            return VerifiedCriterionEvidence(
                domain="observability_operations",
                criterion="traceability",
                repository=repository, assessed_commit=assessed_commit,
                verification_state="observed", source="github_exact_native_v2_artifact",
                evidence=("https://github.com/" + REPO + "/actions/runs/42026802447#sha=" + SHA,),
            )
        with patch("build_readiness_evidence_manifest.verify_existing_crm_v2_traceability",
                   side_effect=proof):
            baseline = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_native_v2=True,
            )
        passed = [r for r in baseline["criteria"] if r["status"] == "passed"]
        self.assertEqual(len(passed), 2)
        self.assertEqual(
            {(r["domain"], r["criterion"]) for r in passed},
            {("test_strategy", "unit_integration"),
             ("observability_operations", "traceability")},
        )
        self.assertFalse(baseline["product_ready"])
        with patch.object(cli, "verify_existing_crm_v2_traceability", side_effect=proof) as verify:
            code, cls, store, output, _ = self.run_cli(baseline, verify_native_v2=True)
        self.assertEqual(code, 0)
        self.assertEqual(verify.call_count, 1)
        persisted = store.persist_product_readiness_certification.call_args.kwargs
        rows = persisted["report"]["criteria"]
        self.assertEqual(rows["observability_operations"]["traceability"]["status"], "passed")
        self.assertEqual(sum(v["status"] == "passed"
                             for table in rows.values() for v in table.values()), 2)
        self.assertFalse(persisted["assessment"].ready)
        self.assertFalse(json.loads(output)["product_ready"])

    def test_verified_v2_proof_disappears_fail_closed_before_persistence(self):
        def proof(repository, assessed_commit, **_):
            return VerifiedCriterionEvidence(
                domain="observability_operations", criterion="traceability",
                repository=repository, assessed_commit=assessed_commit,
                verification_state="observed", source="github_native_v2_source",
                evidence=("evidence#sha=" + SHA,),
            )
        with patch("build_readiness_evidence_manifest.verify_existing_crm_v2_traceability",
                   side_effect=proof):
            baseline = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_native_v2=True,
            )
        with patch.object(cli, "verify_existing_crm_v2_traceability",
                          side_effect=RuntimeError("artifact deleted")):
            with self.assertRaises(RuntimeError):
                self.run_cli(baseline, verify_native_v2=True)

    def test_source_verified_health_creates_only_one_additional_pass(self):
        def proof(repository, assessed_commit, **kwargs):
            return VerifiedCriterionEvidence(
                domain="observability_operations", criterion="health",
                repository=repository, assessed_commit=assessed_commit,
                verification_state="observed", source="live_github_console_cp",
                evidence=("https://github.com/" + REPO + "/actions/runs/7#sha=" + SHA,),
            )
        with patch("build_readiness_evidence_manifest.verify_health_for_certification",
                   side_effect=proof):
            baseline = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda p: github()[p],
                verify_health=True,
            )
        passed = [row for row in baseline["criteria"] if row["status"] == "passed"]
        self.assertEqual(
            {(row["domain"], row["criterion"]) for row in passed},
            {("test_strategy", "unit_integration"),
             ("observability_operations", "health")},
        )
        self.assertFalse(baseline["product_ready"])
        with patch.object(cli, "verify_health_for_certification", side_effect=proof) as again:
            result, _, store, output, _ = self.run_cli(baseline, verify_health=True)
        self.assertEqual(result, 0)
        self.assertEqual(again.call_count, 1)
        attestation = store.persist_product_readiness_certification.call_args.kwargs
        self.assertFalse(attestation["assessment"].ready)
        self.assertEqual(
            attestation["report"]["criteria"]["observability_operations"]["health"]["status"],
            "passed",
        )
        self.assertFalse(json.loads(output)["product_ready"])

    def test_lost_live_health_source_never_persists_a_claim(self):
        from ai_product_factory.independent_health_evidence import HealthEvidenceBlocked
        def proof(repository, assessed_commit, **kwargs):
            return VerifiedCriterionEvidence(
                domain="observability_operations", criterion="health",
                repository=repository, assessed_commit=assessed_commit,
                verification_state="observed", source="live_github_console_cp",
                evidence=("https://github.com/" + REPO + "/actions/runs/7#sha=" + SHA,),
            )
        with patch("build_readiness_evidence_manifest.verify_health_for_certification",
                   side_effect=proof):
            baseline = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda p: github()[p],
                verify_health=True,
            )
        with patch.object(cli, "verify_health_for_certification",
                          side_effect=HealthEvidenceBlocked("health_changed")):
            with self.assertRaises(HealthEvidenceBlocked):
                self.run_cli(baseline, verify_health=True)

    def test_persistence_block_writes_only_sanitized_diagnostic_receipt(self):
        error = RuntimeError(
            "control-plane RPC failed: factory_persist_product_readiness_certification_v1 "
            "(403; code=42501)"
        )
        result, _, store, output, raised = self.run_cli(
            self.baseline(), persist_error=error
        )
        self.assertIsNone(result)
        self.assertIs(raised, error)
        receipt = json.loads(output)
        self.assertEqual(receipt["persistence"], {
            "status": "blocked", "diagnostic": str(error),
        })
        self.assertEqual(receipt["certification"]["run_id"], "run-fixture")
        self.assertFalse(receipt["product_ready"])
        self.assertEqual(store.persist_product_readiness_certification.call_count, 1)

    def test_trusted_workflow_run_renews_oidc_before_allocating_certification(self):
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_run",
        }):
            with patch.object(cli, "refresh_certification_broker_oidc") as refresh:
                code, _, store, _, _ = self.run_cli(self.baseline())
        self.assertEqual(code, 0)
        refresh.assert_called_once_with()
        self.assertEqual(store.begin_product_readiness_certification.call_count, 1)

    def test_oidc_refresh_rejection_prevents_durable_begin_and_persist(self):
        from ai_product_factory.control_plane_oidc_refresh import BrokerOIDCRefreshBlocked
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_run",
        }):
            with patch.object(cli, "refresh_certification_broker_oidc",
                              side_effect=BrokerOIDCRefreshBlocked("broker_oidc_claims_mismatch")):
                with tempfile.TemporaryDirectory() as directory:
                    file = Path(directory) / "verified.json"
                    file.write_text(json.dumps(self.baseline()), encoding="utf-8")
                    argv = [
                        "--project-key", "ai-product-factory",
                        "--repository", REPO,
                        "--assessed-commit", SHA,
                        "--evidence-file", str(file),
                        "--require-verified-baseline",
                    ]
                    with patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only-token"}):
                        with patch.object(cli, "_github_get",
                                          return_value=lambda route: github()[route]):
                            with patch.object(cli, "SupabaseDeliveryStore") as store:
                                with self.assertRaisesRegex(BrokerOIDCRefreshBlocked,
                                                            "broker_oidc_claims_mismatch"):
                                    cli.main(argv)
                                store.assert_not_called()

    def test_missing_health_sources_stay_missing_not_fake_pass(self):
        from ai_product_factory.independent_health_evidence import HealthEvidenceBlocked
        with patch("build_readiness_evidence_manifest.verify_health_for_certification",
                   side_effect=HealthEvidenceBlocked("health_endpoint_blocked")):
            baseline = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda p: github()[p],
                verify_health=True,
            )
        self.assertEqual(
            next(row["status"] for row in baseline["criteria"]
                 if (row["domain"], row["criterion"])
                 == ("observability_operations", "health")),
            "missing",
        )
        self.assertEqual(sum(row["status"] == "passed"
                             for row in baseline["criteria"]), 1)
        self.assertFalse(baseline["product_ready"])

    def test_unsupported_input_or_sha_mismatch_never_writes(self):
        cases = []
        base = self.baseline()
        cases.append(base["manifest"])  # raw manifest forbidden in scheduled mode
        for field, value in [
            ("repository", "attacker/other"),
            ("assessed_commit", "b" * 40),
            ("product_ready", True),
            ("paid_calls", 1),
            ("writes", 1),
            ("start_authorized", True),
            ("scope", "forged"),
        ]:
            bad = json.loads(json.dumps(base))
            bad[field] = value
            cases.append(bad)
        for bad in cases:
            with self.subTest(value=bad.get("scope")):
                with self.assertRaises(CertificationEvidenceError):
                    self.run_cli(bad)

    def test_mutated_source_or_evidence_fails_before_persistence(self):
        for change in ("source_snapshot", "evidence_digest", "assessment", "manifest"):
            with self.subTest(change=change):
                bad = self.baseline()
                if change == "source_snapshot":
                    bad[change]["validation_run_id"] = 999
                elif change == "evidence_digest":
                    bad[change] = "0" * 64
                elif change == "assessment":
                    bad[change]["ready"] = True
                else:
                    bad[change]["criteria"]["security"]["authn_authz"]["status"] = "passed"
                with self.assertRaises(CertificationEvidenceError):
                    self.run_cli(bad)

    def test_stale_main_sha_fails_before_persistence(self):
        with self.assertRaises(CertificationEvidenceError):
            self.run_cli(self.baseline(), sha="b" * 40)

    def test_workflow_is_separate_and_only_on_successful_main_push(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        block = workflow.split("\n  product-readiness-certification-post-ci:", 1)[1].split(
            "\n  global-readiness-post-ci:", 1
        )[0]
        for field in (
            "needs: schedule-probe",
            "always() && github.event_name == 'workflow_run'",
            "github.event_name == 'workflow_run'",
            "github.event.workflow_run.name == 'validate'",
            "github.event.workflow_run.event == 'push'",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.repository.full_name == github.repository",
            "ref: ${{ github.event.workflow_run.head_sha }}",
            "persist-credentials: false",
            "--require-verified-baseline",
            "factory-readiness-persistence-receipt.json",
            "./.github/actions/control-plane-oidc",
        ):
            self.assertIn(field, block)
        self.assertNotIn("run_codex", block)
        self.assertNotIn("run_direct", block)
        self.assertNotIn("model_client", block)
        self.assertNotIn("actions: write", block)
        observer = workflow.split("\n  global-readiness-post-ci:", 1)[1].split(
            "\n  owner-start:", 1
        )[0]
        self.assertNotIn("certify_product_readiness.py", observer)
        self.assertIn("scripts/build_readiness_evidence_manifest.py", observer)
        self.assertIn("--verify-native-v2-traceability", block)
        self.assertEqual(block.count("--verify-independent-health"), 2)
        self.assertLess(
            block.index("uses: ./.github/actions/control-plane-oidc"),
            block.index("scripts/build_readiness_evidence_manifest.py"),
        )
        self.assertLess(
            block.index("scripts/build_readiness_evidence_manifest.py"),
            block.index("scripts/certify_product_readiness.py"),
        )


if __name__ == "__main__":
    unittest.main()
