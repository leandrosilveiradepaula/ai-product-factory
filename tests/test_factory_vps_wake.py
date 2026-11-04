"""Exact workflow dispatch contract: no token disclosure or model use."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/dispatch_factory_vps_wake.py"
SPEC = importlib.util.spec_from_file_location("factory_vps_wake", SCRIPT)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class Response:
    status = 204
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


class VpsWakeTests(unittest.TestCase):
    def test_exact_accepted_workflow_without_model(self):
        calls = []
        def opener(req, *, timeout):
            calls.append((req, timeout))
            return Response()
        self.assertEqual(mod.dispatch(token="fixture-token", opener=opener), "accepted")
        req, timeout = calls[0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(timeout, 12)
        self.assertEqual(req.full_url, mod.URL)
        self.assertEqual(json.loads(req.data), {"ref":"main","inputs":{"vps_wake":"true"}})
        self.assertEqual(req.get_header("Authorization"), "Bearer fixture-token")
        self.assertNotIn("fixture-token", req.data.decode())

    def test_no_network_without_token(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("network request occurred")
        for value in ("", " ", "wrong\ntoken", "wrong\rtoken"):
            with self.subTest(token=value):
                self.assertEqual(mod.dispatch(token=value, opener=forbidden), "missing_token")

    def test_fail_closed_and_never_log_response_body(self):
        for status, expected in (
            (401, "permission_denied"),(403, "permission_denied"),
            (404, "workflow_not_found"),(422,"workflow_input_rejected"),
            (429,"transient_error"),(500,"transient_error"),
        ):
            with self.subTest(status=status):
                def reject(req, *, timeout):
                    raise urllib.error.HTTPError(req.full_url,status,
                        "private-token-in-error",{},io.BytesIO(b"secret-body"))
                self.assertEqual(mod.dispatch(token="fixture",opener=reject),expected)

    def test_transport_failure_is_explicit(self):
        def fail(*args, **kwargs):
            raise urllib.error.URLError("private-url")
        self.assertEqual(mod.dispatch(token="fixture",opener=fail),"transport_error")

    def test_main_prints_only_bounded_receipt(self):
        with patch.dict(os.environ,{"FACTORY_VPS_GITHUB_TOKEN":"fixture-secret"}):
            with patch.object(mod,"dispatch",return_value="permission_denied"):
                with patch("sys.stdout",new_callable=io.StringIO) as stream:
                    self.assertEqual(mod.main(),1)
                self.assertNotIn("fixture-secret",stream.getvalue())
                result=json.loads(stream.getvalue())
                self.assertEqual(result["result"],"permission_denied")
                self.assertEqual(result["calls_to_paid_model"],0)
                self.assertFalse(result["release_authorized"])

    def test_systemd_templates_are_not_self_enabling(self):
        service=(ROOT/"deploy/systemd/ai-product-factory-vps-wake.service").read_text()
        timer=(ROOT/"deploy/systemd/ai-product-factory-vps-wake.timer").read_text()
        self.assertIn("Type=oneshot",service)
        self.assertIn("User=factory-wake",service)
        self.assertIn("EnvironmentFile=/etc/ai-product-factory/vps-wake.env",service)
        self.assertIn("Restart=no",service)
        self.assertIn("Persistent=false",timer)
        self.assertIn("OnCalendar=",timer)
        self.assertNotIn("systemctl enable",timer)

    def test_existing_crm_recovery_lane_accepts_vps_dispatch(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        self.assertIn("vps_wake:",workflow)
        self.assertIn("inputs.vps_wake == true",workflow)
        candidate=workflow.split("  candidate-repin:",1)[1].split("\\n  # Human-merged PR",1)[0]
        self.assertNotIn("github.event_name == 'workflow_dispatch'",candidate)
        self.assertIn("python scripts/run_crm209_native_ci_recovery.py",workflow)
        self.assertIn("FACTORY_CRM209_NATIVE_ENABLED: \"true\"",workflow)


if __name__=="__main__":
    unittest.main()
