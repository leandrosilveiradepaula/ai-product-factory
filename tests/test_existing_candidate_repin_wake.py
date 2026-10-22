"""Offline contract for the isolated, owner-only existing candidate reconciliation lane."""
import unittest
from pathlib import Path
import re

from scripts.summarize_candidate_repin_run import summarize

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/autonomous-runner.yml").read_text(encoding="utf-8")
BROKER = (ROOT / "supabase/functions/factory-runtime-control-plane/index.ts").read_text(encoding="utf-8")
SHA = "a" * 40


def job(name):
    match = re.search(r"(?ms)^  " + re.escape(name) +
                      r":\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)", WORKFLOW)
    if match is None:
        raise AssertionError(f"expected one {name} job")
    return match.group(1)


def example(*, projects=1, eligible=1, limit=3, group=0, outcome="unchanged"):
    groups = (eligible + limit - 1) // limit
    count = min(limit, eligible - group * limit) if groups else 0
    return {
        "status": ("idle" if not eligible else
                   "partial_failure" if outcome in {"blocked", "error"} else "completed"),
        "scanned": projects, "eligible": eligible, "policy_disabled": projects - eligible,
        "limit": limit, "rotation_group": group if groups else None,
        "total_groups": groups, "next_page": groups > 1,
        "results": [
            {"project_key": f"existing-{n:02d}", "status": outcome,
             "sha": SHA, "new_sha": SHA, "reason": "TOKEN_MUST_NOT_LEAK"}
            for n in range(count)
        ],
    }


class ExistingCandidateWakeTests(unittest.TestCase):
    def test_same_existing_cron_without_new_scheduler(self):
        self.assertEqual(WORKFLOW.count("    - cron:"), 2)
        self.assertIn('cron: "17 * * * *"', WORKFLOW)
        self.assertIn('cron: "47 * * * *"', WORKFLOW)
        self.assertEqual(WORKFLOW.count("  candidate-repin:\n"), 1)

    def test_isolated_lane_independent_of_primary_or_queue_preflight(self):
        candidate = job("candidate-repin")
        github = job("github-access-preflight")
        self.assertNotIn("needs: schedule-probe", candidate)
        self.assertNotIn("needs:", candidate.split("    steps:", 1)[0])
        self.assertNotIn("--mode candidate-repin", github)
        self.assertIn("--mode candidate-repin --max-items 3", candidate)
        self.assertIn("scripts/summarize_candidate_repin_run.py", candidate)
        self.assertIn("environment: openai-api", candidate)
        self.assertIn("id-token: write", candidate)

    def test_strict_owner_command_is_not_generic_wake(self):
        candidate = job("candidate-repin")
        head = candidate.split("    runs-on:", 1)[0]
        for match in ("github.event_name == 'schedule'",
                      "github.event_name == 'issue_comment'",
                      "github.event.comment.body == '/factory-candidate-repin'",
                      "github.event.comment.author_association == 'OWNER'",
                      "github.actor == github.event.comment.user.login",
                      "github.event.repository.full_name == github.repository"):
            self.assertIn(match, head)
        self.assertNotIn("'/factory-wake'", head)
        probe = job("schedule-probe").split("    runs-on:", 1)[0]
        self.assertIn("github.event.comment.body == '/factory-wake'", probe)
        self.assertNotIn("/factory-candidate-repin", probe)

    def test_no_paid_keys_write_permissions_or_auto_merge_in_repin_lane(self):
        candidate = job("candidate-repin")
        for forbidden in ("OPENAI_API_KEY:", "FACTORY_PRIMARY_MODEL_ENABLED",
                          "FACTORY_CODEX_ENABLED", "issues: write", "contents: write",
                          "pull-requests: write", "--mode product", "--mode direct",
                          "gh pr merge", "merge_pull_request", "Vercel"):
            self.assertNotIn(forbidden, candidate)
        self.assertIn("FACTORY_GITHUB_TOKEN: ${{ secrets.FACTORY_GITHUB_TOKEN }}", candidate)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", candidate)
        self.assertIn("set -uo pipefail", candidate)
        self.assertIn('exit "$exit_code"', candidate)
        self.assertIn('test -s /tmp/factory-candidate-repin.json', candidate)

    def test_broker_restricts_owner_issue_comment_identity(self):
        self.assertIn('if(event==="issue_comment" && String(payload.actor_id??"")!==EXPECTED.repository_owner_id)', BROKER)
        self.assertIn('"issue_comment"', BROKER)
        self.assertIn("TRUSTED_BACKUP_WORKFLOW_REF", BROKER)
        self.assertIn("mintGithubInstallationToken", BROKER)

    def test_noop_receipt_is_sanitized_and_provable(self):
        out, md = summarize(example())
        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["results"], [
            {"project_key": "existing-00", "status": "unchanged", "sha": SHA}])
        self.assertIn("| existing-00 | unchanged | " + SHA + " |", md)
        self.assertNotIn("TOKEN_MUST_NOT_LEAK", str(out) + md)
        self.assertIn("not global product readiness", md)

    def test_missing_policies_are_explicit_idle(self):
        out, md = summarize(example(projects=1, eligible=0))
        self.assertEqual(out["status"], "idle")
        self.assertEqual(out["results"], [])
        self.assertEqual(out["policy_disabled"], 1)
        self.assertIn("idle (no eligible policies)", md)

    def test_partial_failure_keeps_other_project_results_without_secret_reason(self):
        case = example(projects=2, eligible=2, outcome="error")
        case["results"][1].update(status="unchanged")
        out, md = summarize(case)
        self.assertEqual([row["status"] for row in out["results"]], ["error", "unchanged"])
        self.assertNotIn("TOKEN_MUST_NOT_LEAK", str(out) + md)

    def test_second_rotation_group_is_supported(self):
        out, md = summarize(example(projects=24, eligible=24, limit=3, group=7))
        self.assertEqual(out["rotation_group"], 7)
        self.assertEqual(out["total_groups"], 8)
        self.assertEqual(len(out["results"]), 3)
        self.assertIn("up to 3 candidates", md)

    def test_invalid_counters_or_result_inventory_fail_closed(self):
        for replacement in (
            {"scanned": 101},
            {"scanned": 0},
            {"eligible": 2},
            {"policy_disabled": 1},
            {"limit": 6},
            {"total_groups": 2},
            {"next_page": True},
            {"rotation_group": None},
            {"results": []},
            {"results": [{"status": "unchanged", "project_key": "not valid", "sha": SHA}]},
            {"results": [{"status": "updated", "project_key": "existing-00", "new_sha": "not-a-sha"}]},
            {"results": [{"status": "skipped", "project_key": "existing-00"}]},
        ):
            case = example()
            case.update(replacement)
            with self.subTest(case=replacement), self.assertRaises(ValueError):
                summarize(case)

    def test_inconsistent_status_or_malformed_payload_fail_closed(self):
        for payload in (None, [], {"status": "completed"}, {**example(), "status": "idle"},
                        {**example(outcome="error"), "status": "completed"},
                        {**example(), "status": "partial_failure"}):
            with self.subTest(payload=str(payload)[:40]), self.assertRaises(ValueError):
                summarize(payload)


if __name__ == "__main__":
    unittest.main()
