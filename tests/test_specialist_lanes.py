import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.github_loop import CIState
from ai_product_factory.operational_alerts import OperationalHealth
from ai_product_factory.specialist_lane_queue import SpecialistLaneItem
from ai_product_factory.specialist_lanes import evaluate_operations_lane,evaluate_qa_lane,evaluate_security_lane


BRANCH="factory/change-set-1"


def item(role):
    return SpecialistLaneItem(
        job_id="job",run_id="run",project_key="demo",repository="owner/repo",
        role=role,candidate_commit="abc",pr_number=12,issue_number=7,
        manifest={"preview":{"required_paths":["apps/console/**"]}},
        acceptance_criteria=("works",),branch=BRANCH,
    )


def pr(**changes):
    data=dict(
        number=12,head_sha="abc",head_repository="owner/repo",
        head_ref=BRANCH,base_ref="main",base_sha="mainsha",
        state="open",merged=False,draft=False,
    )
    data.update(changes)
    return SimpleNamespace(**data)


def github_ready():
    github=MagicMock()
    github.get_pull_request.return_value=pr()
    github.get_branch_sha.return_value="abc"
    github.get_pull_request_file_details.return_value=(
        {"filename":"src/core.py","patch":"+value=1","status":"modified",
         "additions":1,"deletions":0},
    )
    github.get_pull_request_files.return_value=("src/core.py",)
    github.get_ci_state.return_value=CIState.SUCCESS
    return github


def healthy_reader():
    reader=MagicMock()
    reader.read.return_value=OperationalHealth(
        unknown_cost_events=0,known_cost=Decimal("0.1")
    )
    return reader


class SpecialistLaneTests(unittest.TestCase):
    def test_security_fails_for_forbidden_security_definer_patch(self):
        github=github_ready()
        github.get_pull_request_file_details.return_value=(
            {"filename":"supabase/migrations/x.sql","patch":"+ security definer",
             "status":"modified","additions":1,"deletions":0},
        )
        out=evaluate_security_lane(item("security"),github)
        self.assertEqual(out.status,"failed")
        self.assertTrue(any(x["code"]=="security_definer" for x in out.findings))
        self.assertFalse(out.evidence["model_call"])
        self.assertEqual(github.get_pull_request.call_count,2)
        github.get_branch_sha.assert_called_once_with(BRANCH)

    def test_security_passes_safe_diff_without_model(self):
        github=github_ready()
        out=evaluate_security_lane(item("security"),github)
        self.assertEqual(out.status,"passed")
        self.assertEqual(out.findings,())
        self.assertFalse(out.evidence["model_call"])
        self.assertTrue(out.evidence["coverage"]["diff_content_available"])

    def test_qa_requires_green_exact_candidate_ci(self):
        github=github_ready()
        out=evaluate_qa_lane(item("qa"),github)
        self.assertEqual(out.status,"passed")
        self.assertEqual(out.evidence["ci_state"],"success")
        self.assertEqual(out.evidence["acceptance_criteria_count"],1)
        self.assertEqual(github.get_pull_request.call_count,2)
        github.get_branch_sha.assert_called_once_with(BRANCH)

    def test_qa_blocks_candidate_identity_change(self):
        github=github_ready()
        github.get_pull_request.return_value=pr(head_sha="different")
        out=evaluate_qa_lane(item("qa"),github)
        self.assertEqual(out.status,"blocked")
        self.assertEqual(out.findings[0]["code"],"candidate_commit_mismatch")
        github.get_ci_state.assert_not_called()

    def test_operations_fails_closed_on_unknown_paid_cost(self):
        github=github_ready()
        github.get_pull_request_files.return_value=("apps/console/app/page.tsx",)
        reader=MagicMock()
        reader.read.return_value=OperationalHealth(
            unknown_cost_events=1,known_cost=Decimal("0.1")
        )
        out=evaluate_operations_lane(item("operations"),github,health_reader=reader)
        self.assertEqual(out.status,"failed")
        self.assertTrue(any(x["code"]=="unknown_cost" for x in out.findings))
        self.assertTrue(out.evidence["preview_required"])
        self.assertEqual(github.get_pull_request.call_count,2)

    def test_security_missing_patch_is_blocked_not_false_green(self):
        github=github_ready()
        github.get_pull_request_file_details.return_value=(
            {"filename":"supabase/migrations/binary.sql","patch":"","status":"modified",
             "additions":1,"deletions":0},
        )
        out=evaluate_security_lane(item("security"),github)
        self.assertEqual(out.status,"blocked")
        self.assertIn("unreviewable_diff",{x["code"] for x in out.findings})
        self.assertFalse(out.evidence["coverage"]["diff_content_available"])
        self.assertIn("diff_content_available",out.evidence["unknowns"])

    def test_security_empty_file_inventory_is_blocked(self):
        github=github_ready()
        github.get_pull_request_file_details.return_value=()
        out=evaluate_security_lane(item("security"),github)
        self.assertEqual(out.status,"blocked")
        self.assertIn("empty_diff_inventory",{x["code"] for x in out.findings})

    def test_untrusted_pr_identity_blocks_all_roles_before_reading_evidence(self):
        scenarios=(
            pr(head_repository="attacker/repo"),
            pr(head_ref="another-branch"),
            pr(number=11),
            pr(state="closed"),
            pr(merged=True),
            pr(draft=True),
            pr(draft=None),
            pr(base_ref=None),
            pr(base_sha=None),
        )
        for role in ("security","qa","operations"):
            for candidate in scenarios:
                with self.subTest(role=role,candidate=candidate):
                    github=github_ready()
                    github.get_pull_request.return_value=candidate
                    out={
                        "security":lambda:evaluate_security_lane(item(role),github),
                        "qa":lambda:evaluate_qa_lane(item(role),github),
                        "operations":lambda:evaluate_operations_lane(item(role),github,health_reader=healthy_reader()),
                    }[role]()
                    self.assertEqual(out.status,"blocked")
                    github.get_pull_request_file_details.assert_not_called()
                    github.get_pull_request_files.assert_not_called()
                    github.get_ci_state.assert_not_called()
                    github.get_branch_sha.assert_not_called()

    def test_pr_changes_during_each_specialist_review_never_passes(self):
        scenarios=(
            ("security",pr(head_sha="new-commit")),
            ("qa",pr(base_sha="new-base")),
            ("operations",pr(state="closed")),
        )
        for role,changed in scenarios:
            with self.subTest(role=role):
                github=github_ready()
                github.get_pull_request.side_effect=[pr(),changed]
                fn={
                    "security":lambda:evaluate_security_lane(item(role),github),
                    "qa":lambda:evaluate_qa_lane(item(role),github),
                    "operations":lambda:evaluate_operations_lane(item(role),github,health_reader=healthy_reader()),
                }[role]
                out=fn()
                self.assertEqual(out.status,"blocked")
                self.assertEqual(github.get_pull_request.call_count,2)
                github.get_branch_sha.assert_not_called()

    def test_branch_moved_after_green_evidence_blocks_all_roles(self):
        for role in ("security","qa","operations"):
            with self.subTest(role=role):
                github=github_ready()
                github.get_branch_sha.return_value="different"
                out={
                    "security":lambda:evaluate_security_lane(item(role),github),
                    "qa":lambda:evaluate_qa_lane(item(role),github),
                    "operations":lambda:evaluate_operations_lane(item(role),github,health_reader=healthy_reader()),
                }[role]()
                self.assertEqual(out.status,"blocked")
                self.assertEqual(out.findings[0]["code"],"candidate_branch_drift")

    def test_invalid_preview_policy_does_not_skip_final_pr_recheck(self):
        github=github_ready()
        github.get_pull_request.side_effect=[pr(),pr(base_ref="preview/something")]
        bad=item("operations")
        bad=SimpleNamespace(**{**bad.__dict__,"manifest":{"preview":{"required_paths":"wrong"}}})
        out=evaluate_operations_lane(bad,github,health_reader=healthy_reader())
        self.assertEqual(out.status,"blocked")
        self.assertEqual(out.findings[0]["code"],"candidate_identity_drift")


if __name__=="__main__":
    unittest.main()
