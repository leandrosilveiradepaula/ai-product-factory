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

    def find_open_issue_containing(self, marker):
        return next((issue for issue in self.issues if marker in issue.body), None)

    def create_issue(self, *, title, body):
        issue = Issue(41, title, body, "https://github.example/issues/41")
        self.issues.append(issue)
        self.created.append(issue)
        return issue


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

    def test_empty_batch_has_no_side_effect(self):
        client = Client()
        self.assertEqual(GitHubIssueAlertAdapter(client).publish_many(()), ())
        self.assertEqual(client.created, [])


if __name__ == "__main__":
    unittest.main()
