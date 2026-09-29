import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.github_loop import CIState
from ai_product_factory.operational_alerts import OperationalHealth
from ai_product_factory.specialist_lane_queue import SpecialistLaneItem
from ai_product_factory.specialist_lanes import evaluate_operations_lane,evaluate_qa_lane,evaluate_security_lane


def item(role):
    return SpecialistLaneItem(
        job_id="job",run_id="run",project_key="demo",repository="owner/repo",
        role=role,candidate_commit="abc",pr_number=12,issue_number=7,
        manifest={"preview":{"required_paths":["apps/console/**"]}},
        acceptance_criteria=("works",),
    )


class SpecialistLaneTests(unittest.TestCase):
    def test_security_fails_for_forbidden_security_definer_patch(self):
        github=MagicMock()
        github.get_pull_request.return_value=SimpleNamespace(head_sha="abc")
        github.get_pull_request_file_details.return_value=(
            {"filename":"supabase/migrations/x.sql","patch":"+ security definer","status":"modified","additions":1,"deletions":0},
        )
        out=evaluate_security_lane(item("security"),github)
        self.assertEqual(out.status,"failed")
        self.assertTrue(any(x["code"]=="security_definer" for x in out.findings))
        self.assertFalse(out.evidence["model_call"])

    def test_security_passes_safe_diff_without_model(self):
        github=MagicMock()
        github.get_pull_request.return_value=SimpleNamespace(head_sha="abc")
        github.get_pull_request_file_details.return_value=(
            {"filename":"src/core.py","patch":"+value=1","status":"modified","additions":1,"deletions":0},
        )
        out=evaluate_security_lane(item("security"),github)
        self.assertEqual(out.status,"passed")
        self.assertEqual(out.findings,())
        self.assertFalse(out.evidence["model_call"])

    def test_qa_requires_green_exact_candidate_ci(self):
        github=MagicMock()
        github.get_pull_request.return_value=SimpleNamespace(head_sha="abc")
        github.get_ci_state.return_value=CIState.SUCCESS
        github.get_pull_request_files.return_value=("src/core.py",)
        out=evaluate_qa_lane(item("qa"),github)
        self.assertEqual(out.status,"passed")
        self.assertEqual(out.evidence["ci_state"],"success")
        self.assertEqual(out.evidence["acceptance_criteria_count"],1)

    def test_qa_blocks_candidate_identity_change(self):
        github=MagicMock()
        github.get_pull_request.return_value=SimpleNamespace(head_sha="different")
        out=evaluate_qa_lane(item("qa"),github)
        self.assertEqual(out.status,"blocked")
        self.assertEqual(out.findings[0]["code"],"candidate_commit_mismatch")

    def test_operations_fails_closed_on_unknown_paid_cost(self):
        github=MagicMock()
        github.get_pull_request.return_value=SimpleNamespace(head_sha="abc")
        github.get_pull_request_files.return_value=("apps/console/app/page.tsx",)
        reader=MagicMock()
        reader.read.return_value=OperationalHealth(
            unknown_cost_events=1,known_cost=Decimal("0.1")
        )
        out=evaluate_operations_lane(item("operations"),github,health_reader=reader)
        self.assertEqual(out.status,"failed")
        self.assertTrue(any(x["code"]=="unknown_cost" for x in out.findings))
        self.assertTrue(out.evidence["preview_required"])


if __name__=="__main__":
    unittest.main()
