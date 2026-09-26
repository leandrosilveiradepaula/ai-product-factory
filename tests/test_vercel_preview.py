import json
import unittest

from ai_product_factory.deployment import DeploymentRequest
from ai_product_factory.evidence import EvidenceBundle
from ai_product_factory.release_policy import ReleaseEnvironment
from ai_product_factory.vercel_preview import VercelPreviewAdapter, VercelPreviewConfig


def deployment_request(environment=ReleaseEnvironment.PREVIEW):
    evidence = EvidenceBundle("abc123", "abc123", "success", metadata={"quality_gate_passed": True})
    return DeploymentRequest("factory", environment, "abc123", evidence)


class Transport:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def __call__(self, method, url, headers, body):
        payload = json.loads(body.decode()) if body else None
        self.calls.append((method, url, headers, payload))
        return 200, self.rows.pop(0)


class Tests(unittest.TestCase):
    def config(self, **overrides):
        values = dict(
            token="token-placeholder",
            team_id="team_1",
            project_name="factory-preview",
            github_org="owner",
            github_repo="repo",
            poll_attempts=3,
            poll_interval_seconds=0,
        )
        values.update(overrides)
        return VercelPreviewConfig(**values)

    def test_refuses_non_preview(self):
        adapter = VercelPreviewAdapter(self.config(), transport=Transport([]), sleeper=lambda _: None)
        with self.assertRaises(PermissionError):
            adapter.deploy(deployment_request(ReleaseEnvironment.PROD))

    def test_requires_explicit_configuration(self):
        with self.assertRaises(ValueError):
            VercelPreviewAdapter(self.config(token=""), transport=Transport([]), sleeper=lambda _: None)

    def test_creates_preview_without_production_target_and_waits_until_ready(self):
        transport = Transport([
            {"id": "dpl_1", "readyState": "BUILDING", "url": "preview.example"},
            {"id": "dpl_1", "readyState": "READY", "url": "preview.example"},
        ])
        result = VercelPreviewAdapter(self.config(), transport=transport, sleeper=lambda _: None).deploy(deployment_request())
        self.assertEqual(result.status, "success")
        self.assertEqual(result.preview_url, "https://preview.example")
        self.assertEqual(result.deployment_ref, "dpl_1")
        create_payload = transport.calls[0][3]
        self.assertNotIn("target", create_payload)
        self.assertEqual(create_payload["gitSource"]["ref"], "abc123")

    def test_terminal_failure_is_returned(self):
        transport = Transport([{"id": "dpl_2", "readyState": "ERROR", "url": "failed.example"}])
        result = VercelPreviewAdapter(self.config(), transport=transport, sleeper=lambda _: None).deploy(deployment_request())
        self.assertEqual(result.status, "failure")

    def test_timeout_is_fail_closed(self):
        transport = Transport([
            {"id": "dpl_3", "readyState": "BUILDING"},
            {"id": "dpl_3", "readyState": "BUILDING"},
            {"id": "dpl_3", "readyState": "BUILDING"},
        ])
        with self.assertRaises(TimeoutError):
            VercelPreviewAdapter(self.config(), transport=transport, sleeper=lambda _: None).deploy(deployment_request())


if __name__ == "__main__":
    unittest.main()
