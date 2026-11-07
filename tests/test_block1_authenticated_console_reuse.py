"""Negative contracts for reusable authenticated Console metadata: never certify JWT/RBAC."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "block1_visual_reuse",
    Path(__file__).resolve().parents[1] / "scripts/verify_block1_authenticated_console_reuse.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SHA = "a" * 40


def fixture():
    run = {
        "id": mod.VISUAL_RUN,
        "name": "Authenticated Console visual evidence",
        "path": mod.VISUAL_WORKFLOW, "event": mod.VISUAL_EVENT, "head_branch": "main",
        "run_attempt": 1, "status": "completed", "conclusion": "success",
        "head_sha": mod.SOURCE_SHA,
    }
    artifacts = {"artifacts": [
        {"name": "authenticated-console-" + str(mod.VISUAL_RUN),
         "expired": False, "size_in_bytes": 1024}
    ]}
    jobs = {"jobs": [{"name": "capture", "status": "completed", "conclusion": "success"}]}
    compare = {"status": "ahead", "behind_by": 0,
               "base_commit": {"sha": mod.SOURCE_SHA},
               "merge_base_commit": {"sha": mod.SOURCE_SHA}}
    tree = {"truncated": False, "tree": [
        {"type": "blob", "path": "apps/console/app/page.tsx",
         "mode": "100644", "sha": "1" * 40},
        {"type": "blob", "path": "scripts/other.py",
         "mode": "100644", "sha": "2" * 40},
    ]}
    import copy
    return [run, artifacts, jobs, compare, tree, copy.deepcopy(tree)]


class AuthenticatedBrowserMetadataTests(unittest.TestCase):
    def test_reuse_metadata_pass_does_not_certify_auth_or_payload(self):
        result = mod.assess(SHA, *fixture())
        self.assertTrue(result["reusable_encrypted_evidence_metadata_verified"], result["checks"])
        for key in ("browser_interaction_payload_independently_reopened",
                    "operator_rbac_log_independently_revalidated",
                    "signed_jwt_issuer_claims_independently_verified",
                    "all_tenant_authorization_covered", "authn_authz_certified",
                    "block1_certified", "release_authorized"):
            self.assertFalse(result[key], key)

    def test_console_blob_or_inventory_drift_denied(self):
        for mutation in ("modified", "new", "removed", "truncated", "duplicate"):
            args = fixture()
            tree = args[-1]
            if mutation == "modified":
                tree["tree"][0]["sha"] = "4" * 40
            elif mutation == "new":
                tree["tree"].append({"type": "blob", "path": "apps/console/new.js",
                                     "mode": "100644", "sha": "4" * 40})
            elif mutation == "removed":
                tree["tree"].remove(tree["tree"][0])
            elif mutation == "truncated":
                tree["truncated"] = True
            elif mutation == "duplicate":
                tree["tree"].append(dict(tree["tree"][0]))
            with self.subTest(mutation=mutation):
                self.assertFalse(mod.assess(SHA, *args)["reusable_encrypted_evidence_metadata_verified"])

    def test_expired_or_missing_artifact_denied(self):
        for mutation in ("expired", "empty", "duplicate"):
            args = fixture()
            if mutation == "expired":
                args[1]["artifacts"][0]["expired"] = True
            elif mutation == "empty":
                args[1]["artifacts"][0]["size_in_bytes"] = 0
            else:
                args[1]["artifacts"].append(dict(args[1]["artifacts"][0]))
            self.assertFalse(mod.assess(SHA, *args)["checks"]["encrypted_artifact_retained"])

    def test_wrong_event_or_identity_or_base_denied(self):
        for mutation in ("wrong_event", "rerun", "untrusted_branch", "failed",
                         "wrong_path", "wrong_source", "wrong_run_id", "behind",
                         "wrong_merge_base"):
            args = fixture()
            if mutation == "wrong_event":
                args[0]["event"] = "push"
            elif mutation == "rerun":
                args[0]["run_attempt"] = 2
            elif mutation == "untrusted_branch":
                args[0]["head_branch"] = "attacker"
            elif mutation == "failed":
                args[0]["conclusion"] = "failure"
            elif mutation == "wrong_path":
                args[0]["path"] = "other.yml"
            elif mutation == "wrong_source":
                args[0]["head_sha"] = "3" * 40
            elif mutation == "wrong_run_id":
                args[0]["id"] = 42
            elif mutation == "behind":
                args[3]["behind_by"] = 1
            else:
                args[3]["merge_base_commit"]["sha"] = "3" * 40
            with self.subTest(mutation=mutation):
                self.assertFalse(mod.assess(SHA, *args)["reusable_encrypted_evidence_metadata_verified"])

    def test_missing_capture_job_denied(self):
        args = fixture()
        args[2]["jobs"][0]["conclusion"] = "failure"
        self.assertFalse(mod.assess(SHA, *args)["reusable_encrypted_evidence_metadata_verified"])

    def test_invalid_sha_is_rejected(self):
        for candidate in ("main", "A" * 40, "a" * 39):
            with self.assertRaises(ValueError):
                mod.assess(candidate, *fixture())


if __name__ == "__main__":
    unittest.main()
