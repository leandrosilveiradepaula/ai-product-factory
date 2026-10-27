import unittest
from dataclasses import dataclass

from ai_product_factory.github_alert_adapter import GitHubIssueAlertAdapter
from ai_product_factory.operational_alerts import OperationalAlert


@dataclass
class Issue:
    number: int
    title: str
    body: str
    html_url: str


class Client:
    def __init__(self):
        self.issues = []
        self.created = []
        self.closed = []
        self.updated = []

    def find_open_issue_containing(self, marker):
        return next((issue for issue in self.issues if marker in issue.body), None)

    def create_issue(self, *, title, body):
        issue = Issue(41, title, body, "https://github.example/issues/41")
        self.issues.append(issue)
        self.created.append(issue)
        return issue

    def update_issue(self, issue_number, *, title, body):
        self.updated.append((issue_number, title, body))
        issue = next(issue for issue in self.issues if issue.number == issue_number)
        issue.title = title
        issue.body = body

    def close_issue(self, issue_number):
        self.closed.append(issue_number)
        self.issues = [issue for issue in self.issues if issue.number != issue_number]


class Tests(unittest.TestCase):
    def test_creates_issue_with_deterministic_marker(self):
        client = Client()
        alert = OperationalAlert("dead_letter", "critical", "two runs exhausted")
        result = GitHubIssueAlertAdapter(client).publish(alert)
        self.assertTrue(result.created)
        self.assertEqual(result.issue_number, 41)
        self.assertIn("factory-alert:dead_letter", client.created[0].body)
        self.assertIn("[critical]", client.created[0].title)

    def test_open_issue_deduplicates_same_alert_code(self):
        client = Client()
        adapter = GitHubIssueAlertAdapter(client)
        alert = OperationalAlert("unknown_cost", "warning", "cost missing")
        first = adapter.publish(alert)
        second = adapter.publish(alert)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(second.issue_number, first.issue_number)


    def test_refreshes_existing_alert_with_current_failed_run_count(self):
        client = Client()
        adapter = GitHubIssueAlertAdapter(client)
        first = adapter.publish(OperationalAlert("failed_runs", "warning", "1 run(s) are failed"))
        current = adapter.publish(OperationalAlert("failed_runs", "warning", "7 run(s) are failed"))
        self.assertFalse(current.created)
        self.assertTrue(current.updated)
        self.assertEqual(first.issue_number, current.issue_number)
        self.assertEqual(1, len(client.issues))
        self.assertEqual(1, len(client.updated))
        self.assertIn("- Message: 7 run(s) are failed\n", client.issues[0].body)
        repeated = adapter.publish(OperationalAlert("failed_runs", "warning", "7 run(s) are failed"))
        self.assertFalse(repeated.created)
        self.assertFalse(repeated.updated)
        self.assertEqual(1, len(client.updated))

    def test_refreshes_severity_preserving_human_notes(self):
        client = Client()
        adapter = GitHubIssueAlertAdapter(client)
        adapter.publish(OperationalAlert("unknown_cost", "warning", "missing usage"))
        client.issues[0].body += "\n## Operator notes\nNever auto-run paid models.\n"
        result = adapter.publish(OperationalAlert("unknown_cost", "critical", "unknown spend"))
        self.assertTrue(result.updated)
        self.assertEqual(client.issues[0].title, "[factory alert][critical] unknown_cost")
        self.assertIn("- Severity: critical\n", client.issues[0].body)
        self.assertIn("## Operator notes\nNever auto-run paid models.", client.issues[0].body)
        self.assertEqual(1, len(client.issues))

    def test_never_rewrites_foreign_template_or_human_retitled_issue(self):
        client = Client()
        adapter = GitHubIssueAlertAdapter(client)
        client.issues.append(Issue(99, "custom incident",
            "<!-- factory-alert:failed_runs -->\noperator notes", "https://github.example/issues/99"))
        result = adapter.publish(OperationalAlert("failed_runs", "warning", "new"))
        self.assertFalse(result.updated)
        self.assertFalse(result.created)
        self.assertEqual([], client.updated)
        self.assertEqual(1, len(client.issues))
        client.issues.clear()
        adapter.publish(OperationalAlert("failed_runs", "warning", "old"))
        client.issues[0].title = "Human-owned investigation"
        result = adapter.publish(OperationalAlert("failed_runs", "warning", "new"))
        self.assertFalse(result.updated)
        self.assertEqual([], client.updated)

    def test_duplicate_marker_in_human_tail_fails_closed(self):
        client = Client()
        adapter = GitHubIssueAlertAdapter(client)
        adapter.publish(OperationalAlert("scheduler_gap", "warning", "last gap 282 minutes"))
        client.issues[0].body += "<!-- factory-alert:scheduler_gap -->\n"
        result = adapter.publish(OperationalAlert("scheduler_gap", "warning", "last gap 123 minutes"))
        self.assertFalse(result.updated)
        self.assertEqual([], client.updated)

    def test_write_error_propagates_without_reporting_update_success(self):
        client = Client()
        adapter = GitHubIssueAlertAdapter(client)
        adapter.publish(OperationalAlert("failed_runs", "warning", "1 failed"))
        def deny(*args, **kwargs):
            raise RuntimeError("GitHub PATCH unavailable")
        client.update_issue = deny
        with self.assertRaisesRegex(RuntimeError, "PATCH unavailable"):
            adapter.publish(OperationalAlert("failed_runs", "warning", "2 failed"))

    def test_rest_client_only_patches_exact_issue_title_and_body(self):
        import json
        from ai_product_factory.github_rest import GitHubRestAdapter
        calls = []
        def transport(method, url, headers, body):
            calls.append((method, url, json.loads(body) if body is not None else None))
            return (200, {})
        github = GitHubRestAdapter(repository="leandrosilveiradepaula/ai-product-factory",
                                  token="offline-unit-token", transport=transport)
        github.update_issue(1048, title="[factory alert][warning] failed_runs", body="current")
        self.assertEqual(calls, [(
            "PATCH", "https://api.github.com/repos/leandrosilveiradepaula/ai-product-factory/issues/1048",
            {"title": "[factory alert][warning] failed_runs", "body": "current"},
        )])
        for invalid in (0, -1, True, "1048"):
            with self.assertRaises(ValueError):
                github.update_issue(invalid, title="valid", body="valid")
        self.assertEqual(len(calls), 1)

    def test_resolves_known_inactive_alert_issue(self):
        client = Client()
        client.issues.append(Issue(
            52,
            "[factory alert][warning] failed_runs",
            "<!-- factory-alert:failed_runs -->\nold",
            "https://github.example/issues/52",
        ))
        adapter = GitHubIssueAlertAdapter(client)
        resolved = adapter.resolve_inactive(
            active_codes=set(),
            known_codes=("failed_runs","unknown_cost"),
        )
        self.assertEqual([52], client.closed)
        self.assertEqual(1, len(resolved))
        self.assertEqual("failed_runs", resolved[0].code)

    def test_active_alert_is_never_closed(self):
        client = Client()
        client.issues.append(Issue(
            53,
            "[factory alert][warning] failed_runs",
            "<!-- factory-alert:failed_runs -->\nactive",
            "https://github.example/issues/53",
        ))
        adapter = GitHubIssueAlertAdapter(client)
        resolved = adapter.resolve_inactive(
            active_codes={"failed_runs"},
            known_codes=("failed_runs",),
        )
        self.assertEqual((), resolved)
        self.assertEqual([], client.closed)

    def test_unknown_marker_is_untouched(self):
        client = Client()
        client.issues.append(Issue(
            54,
            "custom issue",
            "<!-- factory-alert:custom_unknown -->\nkeep",
            "https://github.example/issues/54",
        ))
        adapter = GitHubIssueAlertAdapter(client)
        resolved = adapter.resolve_inactive(
            active_codes=set(),
            known_codes=("failed_runs","unknown_cost"),
        )
        self.assertEqual((), resolved)
        self.assertEqual([], client.closed)
        self.assertEqual(1, len(client.issues))

    def test_empty_batch_has_no_side_effect(self):
        client = Client()
        self.assertEqual(GitHubIssueAlertAdapter(client).publish_many(()), ())
        self.assertEqual(client.created, [])


if __name__ == "__main__":
    unittest.main()
