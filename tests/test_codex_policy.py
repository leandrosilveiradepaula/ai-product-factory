import unittest

from ai_product_factory.codex_policy import classify_codex_need
from ai_product_factory.models import Complexity, TaskProfile


class CodexPolicyTests(unittest.TestCase):
    def test_simple_change_does_not_use_codex(self):
        decision = classify_codex_need(TaskProfile(complexity=Complexity.LOW, estimated_files=2))
        self.assertFalse(decision.should_use)
        self.assertLess(decision.level, 3)

    def test_deep_large_refactor_uses_codex(self):
        decision = classify_codex_need(TaskProfile(
            complexity=Complexity.HIGH,
            estimated_files=30,
            deep_debug=True,
            large_refactor=True,
        ))
        self.assertTrue(decision.should_use)
        self.assertEqual(decision.level, 4)

    def test_medium_change_prefers_direct_execution(self):
        decision = classify_codex_need(TaskProfile(
            complexity=Complexity.MEDIUM,
            estimated_files=5,
            direct_tools_sufficient=True,
        ))
        self.assertFalse(decision.should_use)


if __name__ == "__main__":
    unittest.main()
