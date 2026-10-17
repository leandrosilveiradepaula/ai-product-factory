"""A new continuation should wake the guarded Factory scheduler without losing its durable result."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTROL=(ROOT/"apps/console/lib/control-plane.ts").read_text()
RUNNER=(ROOT/".github/workflows/autonomous-runner.yml").read_text()

class ContinuationAutonomousWakeTests(unittest.TestCase):
    def section(self):
        return CONTROL.split("export async function enqueueProjectContinuation(",1)[1].split(
            "export async function getDashboard()",1
        )[0]

    def test_immediate_wake_after_atomic_commit_and_exact_confirmation(self):
        source=self.section()
        self.assertLess(source.index("rpc/factory_enqueue_project_continuation"),
                        source.index("result.request_id!==requestId"))
        self.assertLess(source.index("result.request_id!==requestId"),
                        source.index("if(result.created){"))
        self.assertLess(source.index("if(result.created){"),
                        source.index("await requestIntakeWorkerWake()"))
        self.assertIn('event_type:"project.continuation.wake_attempted"',source)
        self.assertIn("run_id:String(result.run_id)",source)
        self.assertIn("request_id:requestId",source)

    def test_request_replay_does_not_dispatch_a_second_wake(self):
        source=self.section()
        self.assertEqual(source.count("await requestIntakeWorkerWake()"),1)
        self.assertIn("if(result.created){",source)
        self.assertLess(source.index("if(result.created){"),source.index("await requestIntakeWorkerWake()"))
        self.assertNotIn("await enqueueProjectBootstrap",source)

    def test_dispatch_and_audit_failure_do_not_invalidate_saved_request(self):
        source=self.section()
        self.assertIn('wakeStatus:"requested"|"unconfigured"|"failed"="failed"',source)
        self.assertIn('catch{console.warn("continuation_worker_wake_failed"',source)
        self.assertIn('catch{console.warn("continuation_worker_wake_audit_failed"',source)
        self.assertIn("return {...result,requestId",source)
        self.assertIn("cache:\"no-store\"",source)

    def test_scheduler_gates_and_human_release_remain_independent(self):
        source=self.section()
        self.assertNotIn("OPENAI_API_KEY",source)
        self.assertNotIn("FACTORY_PRIMARY_MODEL_ENABLED=true",source)
        self.assertNotIn("merge_pull_request",source)
        self.assertIn("needs.schedule-probe.outputs.product_work == 'true'",RUNNER)
        self.assertIn("steps.readiness.outputs.primary_model == 'true'",RUNNER)

if __name__=="__main__":
    unittest.main()
