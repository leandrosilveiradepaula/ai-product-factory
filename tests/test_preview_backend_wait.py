"""Adversarial, network-free Preview backend wait/resume tests.

The selected SHA and original failed browser receipt MUST match a real
successful Preview deployment before any outbound, credentialless HTTP probe.
No model, token, browser, migration or release is exercised by this suite.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from ai_product_factory.preview_backend_wait import (
    PreviewBackendWait, evaluate_preview_backend_wait,
)
from ai_product_factory.preview_session_probe import (
    PreviewEnvironmentNotReady, is_session_backend_503,
)
from ai_product_factory.runtime_cli import (
    _external_backend_preview_wait, run_preview_probe_once,
)

RUN="11111111-1111-4111-8111-111111111111"
SHA="a"*40
URL="https://service-desk-preview-example.vercel.app"


def fixtures():
    return {
        "factory_evaluations": [{
            "id":"11111111-2222-4111-8111-111111111111",
            "status":"failure","baseline_ref":URL,
            "result":{"preview_url":URL, "checks":["page_load","http_status"],
                      "detail":"console: server responded 503 | http_503: fetch /api/session"},
        }],
        "factory_deployments": [{
            "status":"success","metadata":{
                "candidate_commit":SHA,"preview_url":URL,"provider":"vercel"},
        }],
    }


def context(rows, *, health="blocked", status="401"):
    calls=[]
    def read(table,params):
        calls.append(("read",table,params))
        return deepcopy(rows[table])
    def probe(url):
        calls.append(("probe",url))
        if health=="blocked":
            raise PreviewEnvironmentNotReady("preview_backend_still_unverified")
        return {"kind":"unauthenticated_json_session_probe",
                "url":url+"/api/session", "http_status":status,
                "content_type":"application/json; charset=utf-8"}
    return read,probe,calls


class BackendWaitTests(unittest.TestCase):
    def test_actual_503_waits_after_verified_sha_and_deployment(self):
        rows=fixtures()
        read,probe,calls=context(rows)
        result=evaluate_preview_backend_wait(
            run_id=RUN,candidate_commit=SHA,read=read,probe=probe)
        self.assertEqual(result, PreviewBackendWait(URL,True,"preview_backend_still_unverified"))
        self.assertEqual([x[0] for x in calls],["read","read","probe"])
        self.assertEqual(calls[0][1],"factory_evaluations")
        self.assertEqual(calls[1][1],"factory_deployments")
        self.assertEqual(calls[2][1],URL)
        self.assertEqual(calls[0][2]["run_id"],"eq."+RUN)
        self.assertEqual(calls[1][2]["status"],"eq.success")
        self.assertEqual(calls[0][2]["order"],"created_at.desc,id.desc")

    def test_real_json_200_or_401_enables_only_new_browser_attempt(self):
        for http_status in ("200","401"):
            with self.subTest(http_status=http_status):
                read,probe,calls=context(fixtures(),health="ready",status=http_status)
                result=evaluate_preview_backend_wait(
                    run_id=RUN,candidate_commit=SHA,read=read,probe=probe)
                self.assertEqual(result,PreviewBackendWait(
                    URL,False,"environment_probe_ready_browser_still_required"))
                self.assertEqual([x[0] for x in calls],["read","read","probe"])
                self.assertFalse(result.waiting)
                self.assertFalse(hasattr(result,"browser_verified"))

    def test_no_previous_failure_is_idle_and_never_probes(self):
        for kind in ("no_rows","success","other_failure"):
            rows=fixtures()
            if kind=="no_rows": rows["factory_evaluations"]=[]
            elif kind=="success": rows["factory_evaluations"][0]["status"]="success"
            else: rows["factory_evaluations"][0]["result"]["detail"]="HTTP 503 from other source"
            read,probe,calls=context(rows)
            self.assertIsNone(evaluate_preview_backend_wait(
                run_id=RUN,candidate_commit=SHA,read=read,probe=probe))
            self.assertEqual([x[0] for x in calls],["read"])

    def test_spoofed_evidence_or_rollback_does_not_probe(self):
        tamper_cases=[
            lambda rows: rows["factory_evaluations"][0].update(
                baseline_ref="https://evil.example.test"),
            lambda rows: rows["factory_evaluations"][0].update(
                baseline_ref="https://example.vercel.app.evil.invalid"),
            lambda rows: rows["factory_evaluations"][0]["result"].update(
                preview_url="https://other.vercel.app"),
            lambda rows: rows["factory_deployments"][0]["metadata"].update(
                candidate_commit="f"*40),
            lambda rows: rows["factory_deployments"][0]["metadata"].update(
                preview_url="https://other.vercel.app"),
            lambda rows: rows["factory_deployments"][0].update(status="failed"),
            lambda rows: rows["factory_deployments"].clear(),
        ]
        for mutate in tamper_cases:
            rows=fixtures()
            mutate(rows)
            read,probe,calls=context(rows)
            with self.subTest(mutate=mutate):
                with self.assertRaises((RuntimeError,PreviewEnvironmentNotReady)):
                    evaluate_preview_backend_wait(
                        run_id=RUN,candidate_commit=SHA,read=read,probe=probe)
                self.assertFalse(any(x[0]=="probe" for x in calls))

    def test_probe_html_or_unauthenticated_response_cannot_skip_browser_gate(self):
        for change in (
            {"url":"https://evil.vercel.app/api/session"},
            {"http_status":"503"},
            {"http_status":"302"},
            {"content_type":"text/html"},
            {"kind":"forged_health"},
        ):
            with self.subTest(change=change):
                read,base_probe,calls=context(fixtures(),health="ready")
                def malformed(url):
                    result=base_probe(url)
                    result.update(change)
                    return result
                with self.assertRaises(RuntimeError):
                    evaluate_preview_backend_wait(
                        run_id=RUN,candidate_commit=SHA,read=read,probe=malformed)

    def test_bad_identity_or_untrusted_json_never_reaches_network(self):
        for bad_run,bad_sha in (("not-a-uuid",SHA),(RUN,"f"*39),(RUN+"x",SHA)):
            read,probe,calls=context(fixtures())
            with self.assertRaises(ValueError):
                evaluate_preview_backend_wait(
                    run_id=bad_run,candidate_commit=bad_sha,read=read,probe=probe)
            self.assertEqual(calls,[])
        for bad_rows in (None,{},[{"status":"failure"},{"status":"failure"}]):
            rows=fixtures()
            rows["factory_evaluations"]=bad_rows
            read,probe,calls=context(rows)
            with self.assertRaises(RuntimeError):
                evaluate_preview_backend_wait(
                    run_id=RUN,candidate_commit=SHA,read=read,probe=probe)
            self.assertFalse(any(x[0]=="probe" for x in calls))

    def test_runtime_wait_receipt_is_not_claimed_for_scheduled_browser(self):
        item=SimpleNamespace(run_id=RUN,candidate_commit=SHA,pr_number=10)
        with patch("ai_product_factory.runtime_cli.SupabasePreviewBackendWaitReader") as reader:
            reader.return_value.check.return_value=PreviewBackendWait(
                URL,True,"preview_backend_still_unverified")
            waiting=_external_backend_preview_wait(item)
            self.assertEqual(waiting["status"],"waiting_external_backend")
            self.assertIs(waiting["claimed"],False)
            self.assertIs(waiting["preview_required"],True)
            self.assertIs(waiting["browser_verified"],False)
            self.assertIs(waiting["release_authorized"],False)
            reader.return_value.check.assert_called_once_with(
                run_id=RUN,candidate_commit=SHA)
            reader.return_value.check.return_value=PreviewBackendWait(
                URL,False,"environment_probe_ready_browser_still_required")
            self.assertIsNone(_external_backend_preview_wait(item))

    def test_real_preview_probe_skips_browser_setup_when_blocked(self):
        item=SimpleNamespace(run_id=RUN,project_id="p",project_key="service-desk",
            candidate_commit=SHA,pr_number=10,
            repository="owner/service-desk",manifest={
                "preview":{"required":True,"provider":"vercel","mode":"github"}})
        pr=SimpleNamespace(state="open",merged=False,head_sha=SHA)
        with (
            patch("ai_product_factory.runtime_cli._next_authorized_preview_with_cursor",
                  return_value=(item,None)),
            patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue"),
            patch("ai_product_factory.runtime_cli.SupabaseFollowupFairCursor"),
            patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github_cls,
            patch("ai_product_factory.runtime_cli._require_current_preview_base"),
            patch("ai_product_factory.runtime_cli.evaluate_preview_applicability") as applicable,
            patch("ai_product_factory.runtime_cli.resolve_project_vercel_preview_config") as cfg,
            patch("ai_product_factory.runtime_cli._external_backend_preview_wait") as wait,
        ):
            github_cls.return_value.get_pull_request.return_value=pr
            github_cls.return_value.get_pull_request_files.return_value=("web/app.tsx",)
            applicable.return_value=SimpleNamespace(required=True)
            cfg.return_value=SimpleNamespace(mode="github")
            wait.return_value={"claimed":False,"status":"waiting_external_backend",
                               "run_id":RUN,"candidate_commit":SHA,
                               "preview_required":True,"browser_verified":False}
            result=run_preview_probe_once()
            self.assertFalse(result["claimed"])
            self.assertEqual(result["status"],"waiting_external_backend")
            self.assertFalse(result["browser_verified"])
            wait.assert_called_once_with(item)
            github_cls.return_value.get_pull_request_files.assert_called_once_with(10)

    def test_only_specific_session_failure_is_environment_block(self):
        self.assertTrue(is_session_backend_503(
            "console 503 | http_503: fetch /api/session"))
        for detail in (None,{"detail":"http_503: fetch /api/session"},
                       "HTTP 503", "http_503: fetch /api/other"):
            self.assertFalse(is_session_backend_503(detail))


if __name__=="__main__":
    unittest.main()
