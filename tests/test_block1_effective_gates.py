"""Adversarial tests: policy inventory is not equivalent to effective protection."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("block1_gates", ROOT / "scripts" / "audit_block1_effective_gates.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def policy(*, strict=False, approval=0, postgres=False):
    checks = [{"context": "test"}, {"context": "factory-acceptance"}]
    if postgres:
        checks.append({"context": "product-readiness-postgres"})
    return [{"id": 1, "enforcement": "active", "rules": [
        {"type": "required_status_checks", "parameters": {
            "required_status_checks": checks,
            "strict_required_status_checks_policy": strict}},
        {"type": "pull_request", "parameters": {"required_approving_review_count": approval}},
        {"type": "deletion"}, {"type": "non_fast_forward"}]}]


class EffectiveGatesTests(unittest.TestCase):
    def test_current_known_policy_gaps_are_not_certified(self):
        result = mod.assess(policy())
        self.assertIn("postgres_qa_not_enforced", result["blockers"])
        self.assertIn("required_checks_not_strict", result["blockers"])
        self.assertIn("approval_count_zero", result["blockers"])
        self.assertFalse(result["regression_gates_certified"])

    def test_missing_ruleset_fails_closed(self):
        result = mod.assess([])
        self.assertIn("no_active_ruleset", result["blockers"])
        self.assertIn("pull_request_not_required", result["blockers"])
        self.assertIn("required_validation_checks_missing", result["blockers"])

    def test_complete_policy_still_does_not_certify_product(self):
        result = mod.assess(policy(strict=True, approval=1, postgres=True))
        self.assertFalse(result["blockers"])
        self.assertFalse(result["regression_gates_certified"])
        self.assertEqual(result["writes"], 0)

    def test_inactive_ruleset_cannot_satisfy_requirements(self):
        rows = policy(strict=True, approval=1, postgres=True)
        rows[0]["enforcement"] = "disabled"
        self.assertIn("no_active_ruleset", mod.assess(rows)["blockers"])

    def test_malformed_inventory_rejected(self):
        with self.assertRaises(ValueError):
            mod.assess({"rulesets": []})

    def test_throttled_token_falls_back_to_real_public_ruleset(self):
        import io
        import json
        import urllib.error
        from unittest.mock import patch
        requests = []
        class Response:
            def __init__(self, value): self.value = value
            def __enter__(self): return io.BytesIO(json.dumps(self.value).encode())
            def __exit__(self, *args): return False
        def open_request(req, timeout):
            requests.append(req)
            if req.get_header("Authorization"):
                raise urllib.error.HTTPError(req.full_url, 403, "rate limited", None, None)
            return Response(policy(strict=True, approval=1, postgres=True)[0])
        with patch.object(mod.urllib.request, "urlopen", side_effect=open_request):
            result = mod._read_public_ruleset("https://api.github.com/repos/example/repo/rulesets/1", "token")
        self.assertEqual(result["id"], 1)
        self.assertEqual(len(requests), 2)
        self.assertIsNone(requests[1].get_header("Authorization"))

    def test_denied_public_ruleset_stays_unverified(self):
        import urllib.error
        from unittest.mock import patch
        def denied(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 403, "denied", None, None)
        with patch.object(mod.urllib.request, "urlopen", side_effect=denied):
            with self.assertRaises(urllib.error.HTTPError):
                mod._read_public_ruleset("https://api.github.com/repos/example/repo/rulesets/1", "token")


if __name__ == "__main__":
    unittest.main()
