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

    def run_cli(self, envelope, *, sha=SHA, verify_native_v2=False):
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
                        store.persist_product_readiness_certification.return_value = {
                            "run_id": "run-fixture",
                            "assessed_commit": SHA,
                            "evaluation_status": "failed",
                        }
                        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                            result = cli.main([
                                "--project-key", "ai-product-factory",
                                "--repository", REPO,
                                "--assessed-commit", sha,
                                "--evidence-file", str(path),
                                "--require-verified-baseline",
                                *(['--verify-native-v2-traceability'] if verify_native_v2 else []),
                            ])
                        return result, cls, store, stdout.getvalue()

    def test_current_sha_baseline_persists_only_not_ready(self):
        envelope = self.baseline()
        result, cls, store, output = self.run_cli(envelope)
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
            code, cls, store, output = self.run_cli(baseline, verify_native_v2=True)
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
