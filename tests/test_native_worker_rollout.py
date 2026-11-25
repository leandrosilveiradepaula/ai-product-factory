import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/factory_native_worker_rollout.py"
spec = importlib.util.spec_from_file_location("rollout", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
TARGET = "a" * 40


class AdmissionTests(unittest.TestCase):
    def test_requires_exact_owner_merge_latest_push_and_both_jobs(self):
        for failure in (None, "owner", "sha", "newer_pending", "job_failed", "job_attempt"):
            def get(path):
                repo = {"full_name": m.REPO}
                if path == "/git/ref/heads/main":
                    return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": TARGET}}
                if path.startswith("/commits/"):
                    return [{"number": 1601, "merge_commit_sha": TARGET, "merged_at": "approved"}]
                if path == "/pulls/1601":
                    return {"number": 1601, "merged": True, "merged_at": "approved",
                            "merge_commit_sha": TARGET, "base": {"ref": "main", "repo": repo},
                            "merged_by": {"id": 0 if failure == "owner" else m.OWNER_ID, "type": "User"}}
                if path.startswith("/actions/workflows/"):
                    run = {"id": 42, "run_number": 1, "run_attempt": 1, "workflow_id": m.VALIDATE_ID,
                           "path": ".github/workflows/validate.yml", "event": "push",
                           "head_sha": "b" * 40 if failure == "sha" else TARGET,
                           "head_branch": "main", "repository": repo, "head_repository": repo,
                           "status": "completed", "conclusion": "success"}
                    rows = [run]
                    if failure == "newer_pending":
                        rows.append({**run, "id": 43, "run_number": 2, "status": "queued", "conclusion": None})
                    return {"total_count": len(rows), "workflow_runs": rows}
                if path == "/actions/runs/42/attempts/1/jobs?per_page=100":
                    jobs = [{"name": n, "head_sha": TARGET, "run_attempt": 1, "status": "completed",
                             "conclusion": "success"} for n in ("test", "factory-acceptance")]
                    if failure == "job_failed":
                        jobs[1]["conclusion"] = "failure"
                    if failure == "job_attempt":
                        jobs[1]["run_attempt"] = 0
                    return {"total_count": 2, "jobs": jobs}
                raise AssertionError(path)
            with self.subTest(failure=failure):
                if failure:
                    with self.assertRaises(m.Blocked):
                        m.admit(get, TARGET)
                else:
                    self.assertEqual(m.admit(get, TARGET), {"sha": TARGET, "pr": 1601, "ci_run": 42, "ci_attempt": 1})
