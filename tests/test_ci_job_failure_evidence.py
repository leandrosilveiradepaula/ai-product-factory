import unittest

from ai_product_factory.ci_job_failure_evidence import parse_failed_native_job_steps

SHA = "a" * 40
REPO = "owner/repo"


def job(*, job_id=21, run=10, attempt=2, sha=SHA, step="Tests",
        conclusion="failure"):
    return {
        "id": job_id, "run_id": run, "run_attempt": attempt,
        "head_sha": sha, "status": "completed", "conclusion": conclusion,
        "steps": ([{"name": step, "status": "completed", "conclusion": "failure"}]
                  if conclusion == "failure" else []),
    }


def parse(jobs, *, count=None):
    return parse_failed_native_job_steps(
        {"total_count": len(jobs) if count is None else count, "jobs": jobs},
        repository=REPO, run_id=10, run_attempt=2, candidate_sha=SHA,
    )


class NativeCIJobFailureTests(unittest.TestCase):
    def test_verified_code_steps_use_closed_labels_and_no_raw_log(self):
        for step in ("Tests", "TypeScript", "Build", "New lint errors",
                     "Dependency audit regression guard"):
            with self.subTest(step=step):
                failures = parse([job(step=step)])
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0].failure_class, "code")
                self.assertIn("native-ci/", failures[0].name)
                self.assertNotIn("secret", str(failures))

    def test_arbitrary_step_cannot_reclassify_infrastructure_as_code(self):
        f = parse([job(step="Setup runner network failed with secret")])
        self.assertEqual(f[0].name, "native-ci/unclassified")
        self.assertEqual(f[0].failure_class, "unknown")
        self.assertNotIn("secret", repr(f))

    def test_no_failed_job_is_not_code_evidence(self):
        self.assertIsNone(parse([job(conclusion="success")]))
        self.assertEqual(parse([job(step="Tests", conclusion="timed_out")])[0].failure_class, "unknown")

    def test_other_sha_and_attempt_are_not_accepted(self):
        for value in (job(sha="b" * 40), job(attempt=1), job(run=11)):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "mismatch"):
                parse([value])

    def test_duplicate_and_truncated_jobs_block(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            parse([job(), job()])
        with self.assertRaisesRegex(RuntimeError, "truncated or unbounded"):
            parse([job()], count=2)
        with self.assertRaisesRegex(RuntimeError, "truncated or unbounded"):
            parse([], count=101)

    def test_empty_inventory_does_not_imply_success(self):
        self.assertIsNone(parse([]))

    def test_too_many_failures_block_the_repair_handoff(self):
        many = [job(job_id=100+i) for i in range(21)]
        with self.assertRaisesRegex(RuntimeError, "bounded repair scope"):
            parse(many)


if __name__ == "__main__":
    unittest.main()
