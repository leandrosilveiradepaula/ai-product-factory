import unittest

from ai_product_factory.deployment import DeploymentCoordinator, DeploymentRequest, DeploymentResult
from ai_product_factory.evidence import EvidenceBundle
from ai_product_factory.release_policy import ReleaseEnvironment


class FakeAdapter:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def deploy(self, request):
        self.calls += 1
        return DeploymentResult(self.name, request.environment, "success", "dep-1", "https://preview.invalid")


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = DeploymentCoordinator()
        self.evidence = EvidenceBundle("a", "b", "success", metadata={"quality_gate_passed": True})

    def test_preview_can_deploy_autonomously(self):
        adapter = FakeAdapter()
        result = self.coordinator.deploy_if_autonomous(
            adapter,
            DeploymentRequest("p", ReleaseEnvironment.PREVIEW, "b", self.evidence),
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(adapter.calls, 1)

    def test_prod_stops_before_adapter(self):
        adapter = FakeAdapter()
        with self.assertRaises(PermissionError):
            self.coordinator.deploy_if_autonomous(
                adapter,
                DeploymentRequest("p", ReleaseEnvironment.PROD, "b", self.evidence),
            )
        self.assertEqual(adapter.calls, 0)

    def test_failed_ci_is_rejected(self):
        bad = EvidenceBundle("a", "b", "failure", metadata={"quality_gate_passed": True})
        with self.assertRaises(ValueError):
            self.coordinator.authorize(
                DeploymentRequest("p", ReleaseEnvironment.PREVIEW, "b", bad)
            )

    def test_mismatched_commit_is_rejected(self):
        with self.assertRaises(ValueError):
            self.coordinator.authorize(
                DeploymentRequest("p", ReleaseEnvironment.PREVIEW, "c", self.evidence)
            )


if __name__ == "__main__":
    unittest.main()
