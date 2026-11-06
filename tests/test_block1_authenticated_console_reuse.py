"""Negative tests: independent browser receipt may be reused only on identical Console blobs."""
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
SOURCE = "b" * 40
JOB = {"name": "capture", "status": "completed", "conclusion": "success"}


def fixture():
    run = {"name": "Authenticated Console visual evidence", "path": mod.VISUAL_WORKFLOW,
           "event": "push", "head_branch": "main", "run_attempt": 1,
           "status": "completed", "conclusion": "success", "head_sha": SOURCE}
    artifacts = {"artifacts": [{"name": "authenticated-console-42100072898",
                               "expired": False, "size_in_bytes": 1024}]}
    jobs = {"jobs": [dict(JOB)]}
    import json
    receipt = {"status": "success", "captured": sorted(mod.REQUIRED_VIEWS),
               "interactionEvidence": {
                   "navigation": [{"status": 200} for _ in range(12)],
                   "operatorRbac": {"href": "/admin/operators",
                                    "finalPath": "/unauthorized", "status": 200}}}
    log = ("Console deployment verified: " + mod.PRODUCTION + " SHA " + SOURCE[:12]
           + " attempts=1\n" + json.dumps(receipt, separators=(",", ":"))
           + "\nConsole deployment verified: " + mod.PRODUCTION
           + " SHA " + SOURCE[:12] + " attempts=1\n")
    compare = {"status": "ahead", "behind_by": 0}
    tree = {"truncated": False, "tree": [
        {"type": "blob", "path": "apps/console/app/page.tsx",
         "mode": "100644", "sha": "1" * 40},
        {"type": "blob", "path": "scripts/other.py",
         "mode": "100644", "sha": "2" * 40},
    ]}
    import copy
    return [run, artifacts, jobs, log, compare, tree, copy.deepcopy(tree)]


class AuthenticatedBrowserReuseTests(unittest.TestCase):
    def test_unchanged_console_reuses_scoped_proof_not_auth_certification(self):
        result = mod.assess(SHA, *fixture())
        self.assertTrue(result["reusable_within_unchanged_console_scope"], result["checks"])
        self.assertFalse(result["signed_jwt_issuer_claims_independently_verified"])
        self.assertFalse(result["authn_authz_certified"])
        self.assertFalse(result["block1_certified"])
        self.assertFalse(result["release_authorized"])

    def test_console_blob_or_inventory_drift_denied(self):
        for mutation in ("modified", "new", "removed", "truncated", "duplicate"):
            args = fixture()
            tree = args[-1]
            entry = {"type": "blob", "path": "apps/console/app/page.tsx",
                     "mode": "100644", "sha": "3" * 40}
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
                tree["tree"].append(entry)
            with self.subTest(mutation=mutation):
                self.assertFalse(mod.assess(SHA, *args)["reusable_within_unchanged_console_scope"])

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

    def test_wrong_event_or_identity_or_merge_denied(self):
        for mutation in ("wrong_event", "rerun", "untrusted_branch", "failed", "wrong_path", "behind"):
            args = fixture()
            if mutation == "wrong_event":
                args[0]["event"] = "workflow_dispatch"
            elif mutation == "rerun":
                args[0]["run_attempt"] = 2
            elif mutation == "untrusted_branch":
                args[0]["head_branch"] = "attacker"
            elif mutation == "failed":
                args[0]["conclusion"] = "failure"
            elif mutation == "wrong_path":
                args[0]["path"] = "other.yml"
            elif mutation == "behind":
                args[4]["behind_by"] = 1
            with self.subTest(mutation=mutation):
                self.assertFalse(mod.assess(SHA, *args)["reusable_within_unchanged_console_scope"])

    def test_missing_negative_rbac_and_invalid_capture_denied(self):
        for mutation in ("rbac", "view", "log", "capture_failed", "no_deployment"):
            args = fixture()
            if mutation == "rbac":
                args[3] = args[3].replace('"/unauthorized"', '"/admin/operators"')
            elif mutation == "view":
                args[3] = args[3].replace('"configuration"', '"duplicate"')
            elif mutation == "log":
                args[3] = args[3].replace('{"status":"success","captured":', '{"status":"failure","captured":')
            elif mutation == "capture_failed":
                args[2]["jobs"][0]["conclusion"] = "failure"
            else:
                args[3] = args[3].replace("Console deployment verified: ", "Unverified deployment: ")
            with self.subTest(mutation=mutation):
                self.assertFalse(mod.assess(SHA, *args)["reusable_within_unchanged_console_scope"])

    def test_invalid_sha_is_rejected(self):
        for candidate in ("main", "A" * 40, "a" * 39):
            with self.assertRaises(ValueError):
                mod.assess(candidate, *fixture())


if __name__ == "__main__":
    unittest.main()
