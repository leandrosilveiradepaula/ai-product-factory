"""Negative tests for read-only Block 1 GitHub evidence."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "block1_live", Path(__file__).resolve().parents[1] / "scripts" / "audit_block1_live_evidence.py"
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
SHA = "a" * 40


def fixtures():
    runs = {
        key: {
            "name": name, "head_sha": SHA, "status": "completed",
            "conclusion": "success", "id": 42,
        }
        for key, name in mod.WORKFLOWS.items()
    }
    rules = {
        "enforcement": "active",
        "rules": [
            {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": "test"}, {"context": "factory-acceptance"}],
            }},
        ],
    }
    artifacts = [{"name": "authenticated-console-42", "expired": False, "size_in_bytes": 10}]
    return runs, rules, artifacts


class LiveEvidenceTests(unittest.TestCase):
    def test_complete_evidence_never_certifies_product(self):
        runs, rules, artifacts = fixtures()
        result = mod.assess(SHA, runs, rules, artifacts)
        self.assertTrue(result["all_verified"])
        self.assertFalse(result["block1_certified"])
        self.assertFalse(result["release_authorized"])

    def test_wrong_sha_fails(self):
        runs, rules, artifacts = fixtures()
        runs["browser"]["head_sha"] = "b" * 40
        self.assertFalse(mod.assess(SHA, runs, rules, artifacts)["all_verified"])

    def test_browser_artifact_missing_fails(self):
        runs, rules, _ = fixtures()
        self.assertFalse(mod.assess(SHA, runs, rules, [])["checks"]["browser_artifact"])

    def test_expired_artifact_fails(self):
        runs, rules, artifacts = fixtures()
        artifacts[0]["expired"] = True
        self.assertFalse(mod.assess(SHA, runs, rules, artifacts)["all_verified"])

    def test_ruleset_review_missing_fails(self):
        runs, rules, artifacts = fixtures()
        rules["rules"][0]["parameters"]["required_approving_review_count"] = 0
        self.assertFalse(mod.assess(SHA, runs, rules, artifacts)["checks"]["ruleset_human_review"])

    def test_non_strict_checks_fail(self):
        runs, rules, artifacts = fixtures()
        rules["rules"][1]["parameters"]["strict_required_status_checks_policy"] = False
        self.assertFalse(mod.assess(SHA, runs, rules, artifacts)["checks"]["ruleset_strict_checks"])

    def test_missing_required_check_fails(self):
        runs, rules, artifacts = fixtures()
        rules["rules"][1]["parameters"]["required_status_checks"] = [{"context": "test"}]
        self.assertFalse(mod.assess(SHA, runs, rules, artifacts)["all_verified"])

    def test_invalid_sha_rejected(self):
        runs, rules, artifacts = fixtures()
        with self.assertRaises(ValueError):
            mod.assess("main", runs, rules, artifacts)


if __name__ == "__main__":
    unittest.main()
