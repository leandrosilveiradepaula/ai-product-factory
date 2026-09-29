import unittest

from ai_product_factory.runtime_worker import DeterministicBootstrapHandler, RuntimeWorker, WorkItem, WorkStatus


class Queue:
    def __init__(self,item): self.item=item; self.events=[]
    def claim_next(self,worker_id): self.events.append(("claim",worker_id)); item,self.item=self.item,None; return item
    def record_stage(self,item,evidence): self.events.append(("stage",evidence.stage,evidence.output["mode"]))
    def complete(self,item): self.events.append(("complete",item.run_id))
    def fail(self,item,error): self.events.append(("fail",item.run_id,error))


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

    def test_worker_returns_none_when_queue_empty(self):
        q=Queue(None)
        self.assertIsNone(RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once())

    def test_worker_fails_closed_on_unknown_stage(self):
        bad=WorkItem("r2","t2","p2","demo",("unknown",),{})
        q=Queue(bad)
        result=RuntimeWorker(queue=q,handler=DeterministicBootstrapHandler(),worker_id="w1").run_once()
        self.assertEqual(result.status,WorkStatus.FAILED)
        self.assertEqual(q.events[-1][0],"fail")


if __name__=="__main__":
    unittest.main()
