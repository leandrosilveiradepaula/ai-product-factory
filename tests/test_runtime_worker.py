import unittest
from dataclasses import replace

from ai_product_factory.runtime_worker import DeterministicBootstrapHandler, RuntimeWorker, WorkItem, WorkStatus


class Queue:
    def __init__(self,item): self.item=item; self.events=[]
    def claim_next(self,worker_id): self.events.append(("claim",worker_id)); item,self.item=self.item,None; return item
    def record_stage(self,item,evidence): self.events.append(("stage",evidence.stage,evidence.output["mode"]))
    def complete(self,item): self.events.append(("complete",item.run_id))
    def fail(self,item,error): self.events.append(("fail",item.run_id,error))


class FencedQueue(Queue):
    def __init__(self, item, fail_at):
        super().__init__(item)
        self.checks = 0
        self.fail_at = fail_at
    def assert_execution_epoch(self, item):
        self.checks += 1
        if self.checks >= self.fail_at:
            raise RuntimeError("execution epoch revoked")


class InstrumentedQueue(Queue):
    def record_stage_event(self,item,stage,status):
        self.events.append(("stage_event",stage,status))


def item():
    return WorkItem("r1","t1","p1","demo",("discovery","specification","planning"),{"summary":"demo"})


class RuntimeWorkerTests(unittest.TestCase):
    def test_worker_executes_bootstrap_in_order_without_model_calls(self):
        q=Queue(item())
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.COMPLETED)
        self.assertEqual([x.stage for x in result.evidence],["discovery","specification","planning"])
        self.assertEqual(q.events[-1],("complete","r1"))
        self.assertTrue(all(x.output["requires_model"] is True for x in result.evidence))

    def test_revocation_before_first_stage_prevents_handler(self):
        q=FencedQueue(item(),1)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertFalse(any(e[0] in {"stage","fail"} for e in q.events))

    def test_revocation_after_first_stage_prevents_persistence(self):
        q=FencedQueue(item(),2)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertFalse(any(e[0] in {"stage","fail"} for e in q.events))

    def test_revoked_epoch_never_records_failed_stage_or_terminal_failure(self):
        class Revoked(FencedQueue):
            def record_stage_event(self, item, stage, status):
                self.events.append(("stage_event", stage, status))
        q=Revoked(item(),2)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertNotIn(("stage_event","discovery","failed"),q.events)
        self.assertFalse(any(event[0]=="fail" for event in q.events))

    def test_error_reporter_failure_does_not_mask_handler_failure(self):
        class FailingReporter(InstrumentedQueue):
            def record_stage_event(self,item,stage,status):
                if status=="failed":
                    raise RuntimeError("reporting unavailable")
                super().record_stage_event(item,stage,status)
            def fail(self,item,error):
                raise RuntimeError("terminal RPC unavailable")
        bad=WorkItem("r","t","p","demo",("unknown",),{})
        result=RuntimeWorker(queue=FailingReporter(bad),handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertIn("unsupported bootstrap stage",result.error)

    def test_pause_between_stage_completion_and_next_stage_blocks_next_handler(self):
        class PausedBetweenStages(FencedQueue):
            def __init__(self, item):
                super().__init__(item, 100)
            def record_stage(self, item, evidence):
                super().record_stage(item, evidence)
                self.fail_at = self.checks + 1
        q=PausedBetweenStages(item())
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertEqual([e.stage for e in result.evidence],["discovery"])
        self.assertFalse(any(e[0]=="fail" for e in q.events))

    def test_revocation_at_final_completion_checkpoint_does_not_complete(self):
        q=FencedQueue(item(),7)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertFalse(any(e[0] in {"complete","fail"} for e in q.events))

    def test_claimed_run_without_stages_does_not_complete(self):
        empty=WorkItem("r","t","p","demo",(),{})
        q=Queue(empty)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertIn("no executable stages",result.error)
        self.assertFalse(any(e[0]=="complete" for e in q.events))
        self.assertTrue(any(e[0]=="fail" for e in q.events))

    def test_handler_must_return_mapping_before_stage_persistence(self):
        class InvalidHandler:
            def execute(self,item,stage):
                return ["not", "a", "mapping"]
        q=Queue(item())
        result=RuntimeWorker(queue=q,handler=InvalidHandler(),worker_id="w").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertIn("must return a mapping",result.error)
        self.assertFalse(any(event[0] in ("stage","complete") for event in q.events))

    def test_missing_stage_sequence_never_reports_success(self):
        malformed=WorkItem("r","t","p","demo",None,{})
        q=Queue(malformed)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertFalse(any(event[0]=="complete" for event in q.events))

    def test_worker_rejects_duplicate_stage_sequence_without_completion(self):
        duplicate=WorkItem("r","t","p","demo",("discovery","discovery"),{})
        q=Queue(duplicate)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertIn("duplicate",result.error)
        self.assertFalse(any(e[0] in ("stage","complete") for e in q.events))

    def test_worker_rejects_malformed_stage_entries(self):
        for stages in ((None,),("  ",),(123,)):
            with self.subTest(stages=stages):
                q=Queue(WorkItem("r","t","p","demo",stages,{}))
                result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
                self.assertEqual(result.status,WorkStatus.FAILED)
                self.assertFalse(any(e[0]=="complete" for e in q.events))

    def test_revoked_malformed_claim_does_not_persist_failure(self):
        for stages in ((), ("discovery", "discovery")):
            with self.subTest(stages=stages):
                q=FencedQueue(WorkItem("r","t","p","demo",stages,{}),1)
                result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
                self.assertEqual(result.status,WorkStatus.FAILED)
                self.assertIn("revoked",result.error)
                self.assertFalse(any(event[0] in {"fail","complete","stage"} for event in q.events))

    def test_malformed_claim_contracts_are_fenced_before_persistence(self):
        baseline=item()
        cases=[
            ({"run_id":""},"run identity"),
            ({"task_id":""},"task identity"),
            ({"project_id":""},"project identity"),
            ({"project_key":""},"project key"),
            ({"context":None},"context"),
            ({"execution_generation":True},"execution generation"),
            ({"execution_generation":-1},"execution generation"),
            ({"worker_id":" "},"worker identity"),
            ({"stages":tuple("s"+str(i) for i in range(33))},"stage limit"),
            ({"stages":("s"*129,)},"oversized stage"),
            ({"stages":(" discovery",)},"unnormalized stage"),
        ]
        for overrides,expected in cases:
            with self.subTest(expected=expected):
                claimed=replace(baseline,**overrides)
                q=Queue(claimed)
                result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
                self.assertEqual(result.status,WorkStatus.FAILED)
                self.assertIn(expected,result.error)
                self.assertFalse(any(event[0] in ("stage","complete") for event in q.events))

    def test_malformed_claim_revocation_suppresses_terminal_write(self):
        for overrides in ({"run_id":""},{"context":None},{"stages":("discovery","discovery")}):
            with self.subTest(overrides=overrides):
                q=FencedQueue(replace(item(),**overrides),1)
                result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w").run_once()
                self.assertEqual(result.status,WorkStatus.FAILED)
                self.assertIn("revoked",result.error)
                self.assertFalse(any(event[0] in ("fail","stage","complete") for event in q.events))

    def test_worker_returns_none_when_queue_empty(self):
        q=Queue(None)
        self.assertIsNone(RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once())

    def test_worker_records_stage_lifecycle_when_queue_supports_it(self):
        q=InstrumentedQueue(item())
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.COMPLETED)
        starts=[x for x in q.events if x[0]=="stage_event" and x[2]=="started"]
        self.assertEqual([x[1] for x in starts],["discovery","specification","planning"])

    def test_worker_records_failed_stage_lifecycle_when_queue_supports_it(self):
        bad=WorkItem("r2","t2","p2","demo",("unknown",),{})
        q=InstrumentedQueue(bad)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertIn(("stage_event","unknown","started"),q.events)
        self.assertIn(("stage_event","unknown","failed"),q.events)

    def test_worker_fails_closed_on_unknown_stage(self):
        bad=WorkItem("r2","t2","p2","demo",("unknown",),{})
        q=Queue(bad)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertEqual(q.events[-1][0],"fail")


if __name__=="__main__":
    unittest.main()
