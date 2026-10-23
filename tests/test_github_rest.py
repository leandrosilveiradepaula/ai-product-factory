import json
import re
import unittest
from unittest.mock import patch

from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubRestAdapter, GitHubCapabilityError


class FakeGitHubTransport:
    def __init__(self):
        self.calls = []
        self.check_runs = [{"name":"test","status":"completed","conclusion":"success","details_url":"https://example/check","head_sha":"commit1","app":{"slug":"github-actions"},"output":{}}]
        self.job_attempts = {}
        self.ci_sha = "commit1"
        self.check_runs_forbidden = False
        self.actions_forbidden = False
        self.workflow_runs = [{"name":"CRM validation","status":"completed","conclusion":"success","head_sha":"commit1","head_branch":"codex/refactor","event":"pull_request","html_url":"https://example/actions/1"}]
        self.commit_statuses = [{"context":"Vercel","state":"success","target_url":"https://preview.example","description":"Deployment completed"}]

    def __call__(self, method, url, headers, body):
        payload = json.loads(body.decode()) if body else None
        self.calls.append((method, url, headers, payload))
        if "/issues/5" in url and method == "GET":
            return 200, {"number": 5, "title": "Feature", "body": "Do it", "html_url": "https://example/issue/5"}
        if "/search/issues?" in url and method == "GET":
            if "is%3Apr" in url:
                return 200, {"items": [{"number": 9, "title": "Manual Codex", "body": "Factory run: run-1", "html_url": "https://example/pr/9", "pull_request": {}}]}
            return 200, {"items": [{"number": 7, "title": "Alert", "body": "<!-- factory-alert:dead_letter -->", "html_url": "https://example/issue/7"}]}
        if "/git/ref/heads/" in url and method == "GET":
            return 200, {"object": {"sha": "base123"}}
        if url.endswith("/git/refs") and method == "POST":
            return 201, {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
        if "/git/commits/base123" in url and method == "GET":
            return 200, {"tree": {"sha": "tree0"}}
        if "/git/trees/tree0?recursive=1" in url and method == "GET":
            return 200, {"truncated": False, "tree": [
                {"path":"AGENTS.md","type":"blob"},
                {"path":"src/app/debug/page.tsx","type":"blob"},
                {"path":"src/app/debug","type":"tree"},
            ]}
        if url.endswith("/git/blobs") and method == "POST":
            return 201, {"sha": "blob1"}
        if url.endswith("/git/trees") and method == "POST":
            return 201, {"sha": "tree1"}
        if url.endswith("/git/commits") and method == "POST":
            return 201, {"sha": "commit1"}
        if "/git/refs/heads/" in url and method == "PATCH":
            return 200, {"object": {"sha": payload["sha"]}}
        if url.endswith("/pulls") and method == "POST":
            return 201, {"number": 9, "html_url": "https://example/pr/9", "head": {"sha": "commit1", "ref": "feat/x", "repo": {"full_name": "owner/repo"}}, "base": {"ref": "main", "sha": "base123"}}
        if "/pulls/9/files" in url and method == "GET":
            return 200, [{"filename":"apps/console/app/page.tsx"},{"filename":"src/core.py"}]
        if "/pulls/9" in url and method == "GET":
            return 200, {"number": 9, "html_url": "https://example/pr/9", "head": {"sha": self.ci_sha, "ref": "codex/refactor", "repo": {"full_name": "owner/repo"}}, "base": {"ref": "main", "sha": "base123"}}
        if "/actions/runs/" in url and "/attempts/" in url and "/jobs?" in url and method == "GET":
            match = re.search(r"/actions/runs/([0-9]+)/attempts/([0-9]+)/jobs[?]", url)
            if not match:
                return 400, {"message": "invalid job request"}
            key = (int(match.group(1)), int(match.group(2)))
            return 200, self.job_attempts.get(key, {"total_count": 0, "jobs": []})
        if "/check-runs" in url and method == "GET":
            if self.check_runs_forbidden:
                return 403, {"message": "forbidden"}
            return 200, {"total_count": len(self.check_runs), "check_runs": self.check_runs}
        if "/actions/runs?" in url and method == "GET":
            if self.actions_forbidden:
                return 403, {"message": "forbidden"}
            return 200, {"total_count": len(self.workflow_runs), "workflow_runs": self.workflow_runs}
        if "/commits/" + self.ci_sha + "/status" in url and method == "GET":
            return 200, {"statuses": self.commit_statuses}
        if "/actions/workflows/validate.yml/dispatches" in url and method == "POST":
            return 204, None
        if "/issues/5" in url and method == "PATCH":
            return 200, {"number": 5, "state": "closed"}
        return 500, {"message": "unexpected"}

class GitHubRestAdapterTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeGitHubTransport()
        self.github = GitHubRestAdapter(repository="owner/repo", token="token-placeholder", transport=self.transport)

    def test_find_open_issue_containing_marker(self):
        issue = self.github.find_open_issue_containing("factory-alert:dead_letter")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.number, 7)
        self.assertIn("search/issues", self.transport.calls[-1][1])

    def test_find_open_pull_request_containing_marker(self):
        pr = self.github.find_open_pull_request_containing("Factory run: run-1")
        self.assertIsNotNone(pr)
        self.assertEqual(pr.number, 9)
        self.assertEqual(pr.head_ref, "codex/refactor")
        self.assertEqual(pr.base_ref, "main")
        self.assertEqual(pr.base_sha, "base123")
        self.assertEqual(pr.head_repository, "owner/repo")

    def test_draft_pr_flag_is_preserved_from_real_github_response(self):
        class DraftResponse(FakeGitHubTransport):
            def __init__(self, draft):
                super().__init__()
                self.draft = draft

            def __call__(self, method, url, headers, body):
                status, row = super().__call__(method, url, headers, body)
                if method == "GET" and url.endswith("/pulls/9"):
                    row = dict(row)
                    if self.draft is not None:
                        row["draft"] = self.draft
                return status, row

        for value in (True, False, None):
            gh = GitHubRestAdapter(repository="owner/repo", token="token-placeholder",
                                   transport=DraftResponse(value))
            with self.subTest(draft=value):
                pr = gh.get_pull_request(9)
                self.assertIs(pr.draft, value)

    def test_token_is_only_in_authorization_header(self):
        self.github.get_issue(5)
        _, _, headers, _ = self.transport.calls[-1]
        self.assertEqual(headers["Authorization"], "Bearer token-placeholder")

    def test_branch_and_atomic_commit(self):
        self.github.create_branch("feat/x")
        sha = self.github.commit_files("feat/x", {"a.py": "print('x')"}, message="feat: x")
        self.assertEqual(sha, "commit1")

    def test_create_pr_and_green_ci(self):
        pr = self.github.create_pull_request(title="x", body="y", head="feat/x")
        self.assertEqual(pr.number, 9)
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)

    def test_pull_request_files_are_structured(self):
        files=self.github.get_pull_request_files(9)
        self.assertEqual(files,("apps/console/app/page.tsx","src/core.py"))

    def test_changed_file_page_two_is_required_for_preview_policy(self):
        from urllib.parse import parse_qs,urlsplit
        from ai_product_factory.preview_policy import evaluate_preview_applicability
        class FilePages(FakeGitHubTransport):
            def __call__(self,method,url,headers,body):
                if "/pulls/9/files?" in url:
                    page=int(parse_qs(urlsplit(url).query).get("page",["1"])[0])
                    if page==1:
                        return 200,[{"filename":f"src/mod_{i:03d}.py"} for i in range(100)]
                    return 200,[{"filename":"apps/console/app/page.tsx"}]
                return super().__call__(method,url,headers,body)
        tr=FilePages()
        gh=GitHubRestAdapter(repository="owner/repo",token="local",transport=tr)
        paths=gh.get_pull_request_files(9)
        self.assertEqual(len(paths),101)
        self.assertTrue(evaluate_preview_applicability(
            manifest={"preview":{"required_paths":["apps/console/**"]}},
            changed_files=paths,
        ).required)
        self.assertEqual(len(gh.get_pull_request_file_details(9)),101)

    def test_renaming_a_console_file_does_not_bypass_preview(self):
        from ai_product_factory.preview_policy import evaluate_preview_applicability
        class Renamed(FakeGitHubTransport):
            def __call__(self,method,url,headers,body):
                if "/pulls/9/files?" in url:
                    return 200,[{"filename":"src/moved.py","status":"renamed",
                                 "previous_filename":"apps/console/app/page.tsx"}]
                return super().__call__(method,url,headers,body)
        gh=GitHubRestAdapter(repository="owner/repo",token="local",transport=Renamed())
        paths=gh.get_pull_request_files(9)
        self.assertEqual(paths,("src/moved.py","apps/console/app/page.tsx"))
        self.assertTrue(evaluate_preview_applicability(
            manifest={"preview":{"required_paths":["apps/console/**"]}},
            changed_files=paths,
        ).required)

    def test_truncated_duplicate_and_oversized_pr_pages_fail_closed(self):
        from urllib.parse import parse_qs,urlsplit
        for mode in ("duplicate","oversized","limit"):
            class InvalidPages(FakeGitHubTransport):
                def __call__(self,method,url,headers,body):
                    if "/pulls/9/files?" in url:
                        page=int(parse_qs(urlsplit(url).query).get("page",["1"])[0])
                        if mode=="oversized":
                            return 200,[{"filename":f"a_{i}.py"} for i in range(101)]
                        if mode=="duplicate":
                            return 200,[{"filename":f"x_{i}.py"} for i in range(100)] if page==1 else [{"filename":"x_0.py"}]
                        return 200,[{"filename":f"page_{page}_{i}.py"} for i in range(100)]
                    return super().__call__(method,url,headers,body)
            gh=GitHubRestAdapter(repository="owner/repo",token="local",transport=InvalidPages())
            with self.subTest(mode=mode),self.assertRaises(RuntimeError):
                gh.get_pull_request_files(9)

    def test_commit_proof_checks_real_sha_without_write(self):
        sha="a"*40
        class Commits(FakeGitHubTransport):
            def __call__(self,method,url,headers,body):
                if "/commits/"+sha in url and method=="GET":
                    return 200,{"sha":sha}
                return super().__call__(method,url,headers,body)
        transport=Commits()
        gh=GitHubRestAdapter(repository="owner/repo",token="local",transport=transport)
        self.assertTrue(gh.commit_exists(sha))
        self.assertEqual(transport.calls,[])
        with self.assertRaises(ValueError):
            gh.commit_exists("unverified")

    def test_repository_file_tree_is_exact_and_blob_only(self):
        paths=self.github.list_file_paths(ref="base123")
        self.assertEqual(paths,("AGENTS.md","src/app/debug/page.tsx"))
    def test_pending_and_failed_ci(self):
        self.transport.check_runs = [{"head_sha":"commit1","app":{"slug":"github-actions"},"status":"in_progress","conclusion":None}]
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.transport.check_runs = [{"head_sha":"commit1","app":{"slug":"github-actions"},"status":"completed","conclusion":"failure"}]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)

    def test_fine_grained_ci_fallback_uses_actions_and_commit_statuses(self):
        self.transport.check_runs_forbidden = True
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)
        self.assertEqual(self.github.last_ci_evidence_source, "github_actions_statuses")
        self.assertTrue(self.github.last_ci_evidence_present)
        urls=[call[1] for call in self.transport.calls]
        self.assertTrue(any("/actions/runs?" in url for url in urls))
        self.assertTrue(any("/commits/commit1/status" in url for url in urls))

    def test_fine_grained_ci_fallback_is_fail_closed_without_workflow_evidence(self):
        self.transport.check_runs_forbidden = True
        self.transport.workflow_runs = []
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.assertFalse(self.github.last_ci_evidence_present)

    def test_fine_grained_ci_fallback_reports_workflow_failure(self):
        self.transport.check_runs_forbidden = True
        self.transport.workflow_runs = [{**self.transport.workflow_runs[0], "conclusion": "failure"}]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)
        failures=self.github.get_failed_checks(9)
        self.assertEqual(failures[0].name,"CRM validation")

    def test_failed_checks_are_structured(self):
        self.transport.check_runs = [{
            "name": "unit-tests",
            "status": "completed",
            "conclusion": "failure",
            "details_url": "https://example/check/1",
            "head_sha": "commit1",
            "app": {"slug": "github-actions"},
            "output": {"summary": "2 tests failed"},
        }]
        failures = self.github.get_failed_checks(9)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].name, "unit-tests")
        self.assertEqual(failures[0].summary, "2 tests failed")

    def test_exact_commit_status_reader_reads_only_full_sha(self):
        sha="a"*40
        class StatusTransport:
            def __call__(self,method,url,headers,body):
                self_call=(method,url)
                assert method=="GET"
                assert url.endswith("/commits/"+sha+"/status")
                return 200,{"statuses":[{"context":"Vercel","state":"success"}]}
        reader=GitHubRestAdapter(repository="owner/repo",token="test-token",transport=StatusTransport())
        self.assertEqual(reader.get_commit_statuses(sha),[{"context":"Vercel","state":"success"}])
        with self.assertRaises(ValueError):
            reader.get_commit_statuses("short")

    def test_explicit_workflow_dispatch_targets_candidate_ref(self):
        self.github.dispatch_workflow("validate.yml",ref="factory/change-set-abc")
        method,url,_,payload=self.transport.calls[-1]
        self.assertEqual(method,"POST")
        self.assertIn("/actions/workflows/validate.yml/dispatches",url)
        self.assertEqual(payload,{"ref":"factory/change-set-abc"})

    def test_vercel_only_green_check_is_never_treated_as_green_ci(self):
        self.transport.check_runs = [{
            "name": "Vercel Preview Comments", "status": "completed",
            "conclusion": "success", "head_sha": "commit1",
            "app": {"slug": "vercel"},
        }]
        self.transport.workflow_runs = []
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.assertFalse(self.github.last_ci_evidence_present)

    def test_github_job_green_while_workflow_pending_does_not_pass(self):
        self.transport.workflow_runs[0]["status"] = "in_progress"
        self.transport.workflow_runs[0]["conclusion"] = None
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.assertTrue(self.github.last_ci_evidence_present)

    def test_workflow_failure_blocks_even_if_partial_check_is_green(self):
        self.transport.workflow_runs[0]["conclusion"] = "failure"
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)
        failures = self.github.get_failed_checks(9)
        self.assertTrue(any(f.name=="CRM validation" for f in failures))

    def test_stale_branch_or_sha_run_does_not_authorize_ci(self):
        for key, invalid in (("head_sha", "other"), ("head_branch", "main"),
                             ("event", "schedule")):
            with self.subTest(key=key):
                old=self.transport.workflow_runs[0][key]
                self.transport.workflow_runs[0][key]=invalid
                self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
                self.assertFalse(self.github.last_ci_evidence_present)
                self.transport.workflow_runs[0][key]=old

    def test_actions_read_capability_is_mandatory_even_with_green_check(self):
        self.transport.actions_forbidden = True
        with self.assertRaisesRegex(GitHubCapabilityError,"Actions: read"):
            self.github.get_ci_state(9)

    def test_preview_status_is_distinct_from_trusted_ci_gate(self):
        self.transport.commit_statuses = [{"context":"Vercel","state":"pending"}]
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)
        # A Vercel status does not bypass the independent verified Preview gate.

    def test_all_skipped_jobs_are_not_successful_validation(self):
        self.transport.check_runs[0]["conclusion"]="skipped"
        self.transport.workflow_runs[0]["conclusion"]="skipped"
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)

    def test_missing_check_runs_with_real_workflow_does_not_trigger_dispatch(self):
        self.transport.check_runs=[]
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.assertTrue(self.github.last_ci_evidence_present)

    def test_oversized_check_or_workflow_inventory_fails_closed(self):
        original_checks = list(self.transport.check_runs)
        original_runs = list(self.transport.workflow_runs)
        self.transport.check_runs=original_checks*101
        with self.assertRaisesRegex(RuntimeError,"100-run limit"):
            self.github.get_ci_state(9)
        self.transport.check_runs=original_checks
        self.transport.workflow_runs=original_runs*101
        with self.assertRaisesRegex(RuntimeError,"100-run limit"):
            self.github.get_ci_state(9)

    @staticmethod
    def _workflow_attempt(*, run_id, suite, conclusion, workflow_id=707,
                          event="pull_request", name="validate", status="completed",
                          attempt=1):
        return {
            "id": run_id, "run_attempt": attempt, "workflow_id": workflow_id,
            "check_suite_id": suite, "name": name, "status": status,
            "conclusion": conclusion, "head_sha": "commit1",
            "head_branch": "codex/refactor", "event": event,
            "html_url": "https://example/actions/" + str(run_id),
        }

    @staticmethod
    def _check_attempt(*, check_id, suite, conclusion, name="unit-tests",
                       status="completed"):
        return {
            "id": check_id, "name": name, "head_sha": "commit1",
            "status": status, "conclusion": conclusion,
            "check_suite": {"id": suite},
            "app": {"slug": "github-actions"},
            "details_url": "https://example/jobs/" + str(check_id),
            "output": {"summary": "tests failed" if conclusion == "failure" else ""},
        }

    def test_new_successful_retry_replaces_old_failure_on_same_sha(self):
        old = self._workflow_attempt(run_id=10, suite=100, conclusion="failure")
        new = self._workflow_attempt(run_id=11, suite=101, conclusion="success")
        self.transport.workflow_runs = [old, new]  # Deliberately oldest first.
        self.transport.check_runs = [
            self._check_attempt(check_id=21, suite=100, conclusion="failure"),
            self._check_attempt(check_id=22, suite=101, conclusion="success"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)
        self.assertEqual(self.github.get_failed_checks(9), ())
        self.assertEqual(
            [row["id"] for row in self.github.last_ci_workflow_runs], [11]
        )

    def test_new_failed_retry_overrides_old_success_and_yields_only_current_failure(self):
        old = self._workflow_attempt(run_id=10, suite=100, conclusion="success")
        new = self._workflow_attempt(run_id=11, suite=101, conclusion="failure")
        self.transport.workflow_runs = [new, old]  # Reverse listing order.
        self.transport.check_runs = [
            self._check_attempt(check_id=21, suite=100, conclusion="failure", name="stale-failure"),
            self._check_attempt(check_id=22, suite=101, conclusion="failure", name="unit-tests"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)
        failures = self.github.get_failed_checks(9)
        self.assertTrue(any(f.name == "unit-tests" and f.failure_class == "code" for f in failures))
        self.assertFalse(any(f.name == "stale-failure" for f in failures))

    def test_new_pending_retry_never_inherits_old_green(self):
        old = self._workflow_attempt(run_id=10, suite=100, conclusion="success")
        new = self._workflow_attempt(run_id=11, suite=101, conclusion=None, status="in_progress")
        self.transport.workflow_runs = [old, new]
        self.transport.check_runs = [
            self._check_attempt(check_id=21, suite=100, conclusion="success"),
            self._check_attempt(check_id=22, suite=101, conclusion=None, status="in_progress"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.assertEqual(self.github.get_failed_checks(9), ())

    def test_independent_workflow_ids_still_require_both_results(self):
        first = self._workflow_attempt(run_id=10, suite=100, conclusion="success", workflow_id=707)
        second = self._workflow_attempt(run_id=11, suite=101, conclusion="failure", workflow_id=708)
        self.transport.workflow_runs = [first, second]
        self.transport.check_runs = [
            self._check_attempt(check_id=21, suite=100, conclusion="success"),
            self._check_attempt(check_id=22, suite=101, conclusion="failure", name="build"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)
        self.assertEqual(len(self.github.last_ci_workflow_runs), 2)

    def test_manual_dispatch_success_cannot_hide_pull_request_failure(self):
        failed_pr = self._workflow_attempt(run_id=10, suite=100, conclusion="failure")
        manual = self._workflow_attempt(
            run_id=11, suite=101, conclusion="success", event="workflow_dispatch"
        )
        self.transport.workflow_runs = [failed_pr, manual]
        self.transport.check_runs = [
            self._check_attempt(check_id=21, suite=100, conclusion="failure"),
            self._check_attempt(check_id=22, suite=101, conclusion="success"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)

    def test_unrelated_issue_comment_suite_cannot_grant_green_ci(self):
        self.transport.workflow_runs = [
            self._workflow_attempt(run_id=10, suite=100, conclusion="success"),
            self._workflow_attempt(
                run_id=11, suite=101, conclusion="success", event="issue_comment"
            ),
        ]
        self.transport.check_runs = [
            self._check_attempt(check_id=22, suite=101, conclusion="success")
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.assertTrue(self.github.last_ci_evidence_present)

    def test_latest_job_retry_in_same_check_suite_wins(self):
        self.transport.workflow_runs = [
            self._workflow_attempt(
                run_id=10, suite=100, conclusion="success", attempt=2
            )
        ]
        self.transport.check_runs = [
            self._check_attempt(check_id=21, suite=100, conclusion="failure"),
            self._check_attempt(check_id=22, suite=100, conclusion="success"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)
        self.assertEqual(self.github.get_failed_checks(9), ())

    def test_newer_attempt_on_same_workflow_run_id_replaces_prior_attempt(self):
        self.transport.workflow_runs = [
            self._workflow_attempt(
                run_id=10, suite=100, conclusion="failure", attempt=1
            ),
            self._workflow_attempt(
                run_id=10, suite=100, conclusion="success", attempt=2
            ),
        ]
        self.transport.check_runs = [
            self._check_attempt(check_id=21, suite=100, conclusion="failure"),
            self._check_attempt(check_id=22, suite=100, conclusion="success"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)
        self.assertEqual(self.github.get_failed_checks(9), ())

    def test_missing_retry_ids_or_mixed_suite_identity_fail_closed(self):
        old = self._workflow_attempt(run_id=10, suite=100, conclusion="failure")
        new = self._workflow_attempt(run_id=11, suite=101, conclusion="success")
        old.pop("id")
        self.transport.workflow_runs = [old, new]
        with self.assertRaisesRegex(RuntimeError, "ambiguous GitHub Actions workflow"):
            self.github.get_ci_state(9)
        self.transport.workflow_runs = [new]
        self.transport.check_runs = [{
            **self._check_attempt(check_id=22, suite=101, conclusion="success"),
            "check_suite": None,
        }]
        with self.assertRaisesRegex(RuntimeError, "verifiable check suite"):
            self.github.get_ci_state(9)

    def test_fallback_without_check_runs_retries_latest_workflow_only(self):
        self.transport.check_runs_forbidden = True
        self.transport.workflow_runs = [
            self._workflow_attempt(run_id=10, suite=100, conclusion="failure"),
            self._workflow_attempt(run_id=11, suite=101, conclusion="success"),
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)
        self.assertEqual(self.github.last_ci_evidence_source, "github_actions_statuses")
        self.assertEqual(self.github.get_failed_checks(9), ())

    def test_fallback_failed_ci_excludes_unrelated_deployment_statuses(self):
        self.transport.check_runs_forbidden = True
        self.transport.workflow_runs = [
            self._workflow_attempt(run_id=10, suite=100, conclusion="failure",
                                   name="unit-tests")
        ]
        self.transport.commit_statuses = [
            {"context": "Vercel - Preview", "state": "failure",
             "description": "deployment billing quota reached"}
        ]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)
        failures = self.github.get_failed_checks(9)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].name, "unit-tests")
        self.assertEqual(failures[0].failure_class, "code")


    def _use_exact_native_candidate(self):
        sha = "a" * 40
        self.transport.ci_sha = sha
        self.transport.workflow_runs = [{
            **self._workflow_attempt(
                run_id=10, suite=100, conclusion="failure", name="CRM validation"
            ),
            "head_sha": sha,
        }]
        check = {**self._check_attempt(
            check_id=20, suite=100, conclusion="failure", name="validate"
        ), "head_sha": sha, "output": {}}
        self.transport.check_runs = [check]
        return sha

    @staticmethod
    def _native_job(*, run_id=10, attempt=1, candidate="commit1",
                    job_id=300, step_name="Tests", conclusion="failure"):
        return {
            "id": job_id, "run_id": run_id, "run_attempt": attempt,
            "head_sha": candidate, "status": "completed",
            "name": "validate", "conclusion": conclusion,
            "steps": ([{"name": step_name, "status": "completed", "conclusion": "failure"}]
                      if conclusion == "failure" else []),
        }

    def test_exact_native_failed_test_step_enters_bounded_code_repair(self):
        sha = self._use_exact_native_candidate()
        self.transport.job_attempts[(10, 1)] = {
            "total_count": 2, "jobs": [
                self._native_job(run_id=10, candidate=sha, step_name="Tests"),
                self._native_job(run_id=10, candidate=sha, job_id=301, conclusion="success"),
            ],
        }
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)
        failure, = self.github.get_failed_checks(9, expected_head_sha=sha)
        self.assertEqual(failure.name, "native-ci/tests")
        self.assertEqual(failure.failure_class, "code")
        self.assertIn("/runs/10/job/300", failure.details_url)
        self.assertNotIn("unknown", repr(failure))
        self.assertTrue(any("/attempts/1/jobs?" in row[1] for row in self.transport.calls))
        self.assertFalse(any("/actions/runs/10/jobs?" in row[1] for row in self.transport.calls))

    def test_verified_native_lint_repair_receives_sanitized_exact_diagnostics(self):
        sha = self._use_exact_native_candidate()
        self.transport.job_attempts[(10, 1)] = {
            "total_count": 1, "jobs": [
                self._native_job(
                    run_id=10, candidate=sha, step_name="New lint errors",
                )
            ],
        }
        text = (
            "2026-10-23T18:33:18Z LINT_CHANGED_ERROR "
            "src/app/(dashboard)/reports/client-page.tsx:121:45 "
            "@typescript-eslint/no-explicit-any Unexpected any and SECRET=never-return-me"
        )
        called = []
        def bounded_reader(job_id):
            called.append(job_id)
            return text
        gh = GitHubRestAdapter(
            repository="owner/repo", token="local", transport=self.transport,
            native_log_reader=bounded_reader,
        )
        failure, = gh.get_failed_checks(9, expected_head_sha=sha)
        self.assertEqual(failure.name, "native-ci/lint")
        self.assertEqual(failure.failure_class, "code")
        self.assertIn(
            "src/app/(dashboard)/reports/client-page.tsx:121:45 "
            "@typescript-eslint/no-explicit-any", failure.summary,
        )
        self.assertNotIn("Unexpected any", failure.summary)
        self.assertNotIn("SECRET", failure.summary)
        self.assertNotIn("never-return-me", failure.summary)
        self.assertEqual(called, [300])
        self.assertIn("attempt", failure.summary)

    def test_native_lint_falls_back_to_generic_without_safe_log_evidence(self):
        sha = self._use_exact_native_candidate()
        self.transport.job_attempts[(10, 1)] = {
            "total_count": 1,
            "jobs": [self._native_job(run_id=10, candidate=sha, step_name="New lint errors")],
        }
        for reader in (
            lambda job_id: "Some other error with no allowlisted marker",
            lambda job_id: (_ for _ in ()).throw(RuntimeError("no logs")),
        ):
            with self.subTest(reader=reader):
                gh = GitHubRestAdapter(
                    repository="owner/repo", token="local", transport=self.transport,
                    native_log_reader=reader,
                )
                failure, = gh.get_failed_checks(9, expected_head_sha=sha)
                self.assertEqual(failure.name, "native-ci/lint")
                self.assertEqual(
                    failure.summary, "Verified failed GitHub Actions step (run and attempt bound)",
                )

    def test_native_job_without_failed_step_never_invents_a_code_patch(self):
        sha = self._use_exact_native_candidate()
        for steps in ([], [{"name": "Initialize containers", "status": "completed",
                            "conclusion": "failure"}]):
            with self.subTest(steps=steps):
                self.transport.job_attempts[(10, 1)] = {
                    "total_count": 1,
                    "jobs": [{**self._native_job(run_id=10, candidate=sha), "steps": steps}],
                }
                failures = self.github.get_failed_checks(9)
                self.assertTrue(failures)
                self.assertTrue(all(f.failure_class == "unknown" for f in failures))

    def test_mixed_code_and_unclassified_failures_are_not_repairable(self):
        sha = self._use_exact_native_candidate()
        self.transport.job_attempts[(10, 1)] = {
            "total_count": 2, "jobs": [
                self._native_job(run_id=10, candidate=sha, job_id=300, step_name="Tests"),
                self._native_job(run_id=10, candidate=sha, job_id=301, step_name="Initialize containers"),
            ],
        }
        failures = self.github.get_failed_checks(9)
        self.assertEqual({f.failure_class for f in failures}, {"code", "unknown"})

    def test_latest_rerun_attempt_only_never_uses_old_job_evidence(self):
        sha = self._use_exact_native_candidate()
        self.transport.workflow_runs[0]["run_attempt"] = 2
        self.transport.job_attempts[(10, 1)] = {
            "total_count": 1, "jobs": [self._native_job(run_id=10, attempt=1, candidate=sha, step_name="Tests")],
        }
        self.transport.job_attempts[(10, 2)] = {
            "total_count": 1,
            "jobs": [self._native_job(run_id=10, attempt=2, candidate=sha,
                                      step_name="Prepare pinned Playwright")],
        }
        failures = self.github.get_failed_checks(9)
        self.assertEqual([f.failure_class for f in failures], ["unknown"])
        self.assertTrue(any("/attempts/2/jobs?" in row[1] for row in self.transport.calls))
        self.assertFalse(any("/attempts/1/jobs?" in row[1] for row in self.transport.calls))

    def test_spoofed_native_job_sha_and_unbounded_inventory_fail_closed(self):
        self._use_exact_native_candidate()
        self.transport.job_attempts[(10, 1)] = {
            "total_count": 1,
            "jobs": [self._native_job(run_id=10, candidate="other-candidate")],
        }
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            self.github.get_failed_checks(9)
        self.transport.job_attempts[(10, 1)] = {"total_count": 101, "jobs": []}
        with self.assertRaisesRegex(RuntimeError, "truncated or unbounded"):
            self.github.get_failed_checks(9)

    def test_adapter_exposes_no_merge_operation(self):
        self.assertFalse(hasattr(self.github, "merge_pull_request"))

    def test_missing_token_fails_fast(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(ValueError):
                GitHubRestAdapter(repository="owner/repo", token="", transport=self.transport)

if __name__ == "__main__":
    unittest.main()
