"""Adversarial tests for owner-only manual release gate observation."""
import importlib.util
from pathlib import Path
import unittest

script = Path(__file__).resolve().parents[1] / "scripts/audit_block1_owner_merge_evidence.py"
spec = importlib.util.spec_from_file_location("block1_owner_release", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SHA = "a" * 40


def fixture():
    pr = {
        "merged": True, "merged_at": "2026-11-05T21:43:03Z",
        "merge_commit_sha": SHA,
        "merged_by": {"login": mod.OWNER, "type": "User"},
        "base": {"ref": "main", "repo": {"full_name": mod.REPO}},
    }
    rules = {
        "enforcement": "active", "target": "branch",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"]}},
        "bypass_actors": [],
        "rules": [
            {"type": "pull_request", "parameters": {"required_approving_review_count": 0}},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [
                    {"context": "test"}, {"context": "factory-acceptance"}],
            }},
            {"type": "non_fast_forward"}, {"type": "deletion"},
        ],
    }
    main = {"name": "main", "commit": {"sha": SHA}}
    return pr, rules, main


class OwnerGateEvidenceTests(unittest.TestCase):
    def test_single_owner_exact_merge_is_observed_not_certified(self):
        pr, rules, main = fixture()
        report = mod.assess(SHA, pr, rules, main)
        self.assertTrue(report["observation_verified"])
        self.assertFalse(report["physical_human_action_proven"])
        self.assertFalse(report["automation_absence_proven"])
        self.assertFalse(report["block1_certified"])
        self.assertFalse(report["release_authorized"])

    def test_no_owner_actor_is_not_human_merge_evidence(self):
        for login, actor_type in [("some-bot[bot]", "Bot"), ("intruder", "User"), ("", "User")]:
            pr, rules, main = fixture()
            pr["merged_by"] = {"login": login, "type": actor_type}
            self.assertFalse(mod.assess(SHA, pr, rules, main)["observation_verified"])

    def test_ruleset_bypass_or_non_strict_invalidates(self):
        for tamper in ("bypass", "strict", "missing_check", "force_push", "approval"):
            pr, rules, main = fixture()
            if tamper == "bypass":
                rules["bypass_actors"] = [{"actor_type": "OrganizationAdmin", "bypass_mode": "always"}]
            if tamper == "strict":
                rules["rules"][1]["parameters"]["strict_required_status_checks_policy"] = False
            if tamper == "missing_check":
                rules["rules"][1]["parameters"]["required_status_checks"] = [{"context": "test"}]
            if tamper == "force_push":
                rules["rules"] = [r for r in rules["rules"] if r["type"] != "non_fast_forward"]
            if tamper == "approval":
                rules["rules"][0]["parameters"]["required_approving_review_count"] = 1
            with self.subTest(tamper=tamper):
                self.assertFalse(mod.assess(SHA, pr, rules, main)["observation_verified"])

    def test_wrong_sha_or_unmerged_or_wrong_branch_invalidates(self):
        for tamper in ("sha", "unmerged", "branch", "owner_repo"):
            pr, rules, main = fixture()
            if tamper == "sha":
                main["commit"]["sha"] = "b" * 40
            elif tamper == "unmerged":
                pr["merged"] = False
            elif tamper == "branch":
                pr["base"]["ref"] = "develop"
            elif tamper == "owner_repo":
                pr["base"]["repo"]["full_name"] = "untrusted/repository"
            with self.subTest(tamper=tamper):
                self.assertFalse(mod.assess(SHA, pr, rules, main)["observation_verified"])

    def test_invalid_sha_rejected(self):
        pr, rules, main = fixture()
        for sha in ("main", "B" * 40, "0" * 39):
            with self.assertRaises(ValueError):
                mod.assess(sha, pr, rules, main)


if __name__ == "__main__":
    unittest.main()
