import unittest
from types import SimpleNamespace
from decimal import Decimal

from ai_product_factory.admission_diagnostics import classify, SupabaseAdmissionReader

P="11111111-1111-4111-8111-111111111111"
T="22222222-2222-4222-8222-222222222222"
R="33333333-3333-4333-8333-333333333333"
OTHER="44444444-4444-4444-8444-444444444444"

def snapshot(state="running", status=None, cost=None, commands=None, planned=None, portfolio=None):
    return dict(project={"id":P,"project_key":"demo","is_active":True},
       control={"project_id":P,"state":state},
       commands=commands or [],tasks=[{"id":T,"project_id":P,"status":"queued"}] if status else [],
       runs=[{"id":R,"task_id":T,"status":status}] if status else [],
       run_id=R if status else None,
       cost=cost or {"state":"available","reason":"within_budget"},
       planned=planned or [],portfolio=portfolio or [])

class AdmissionTests(unittest.TestCase):
    def test_control_states_never_claim(self):
        for state in ("draft","paused","pausing","stopped","stopping"):
            with self.subTest(state=state):
                x=classify(**snapshot(state=state,status="queued"))
                self.assertEqual(x["status"],"blocked")
                self.assertEqual(x["reason_code"],"project_"+state)

    def test_start_pending_bootstrap_and_missing_start(self):
        self.assertEqual(classify(**snapshot())["reason_code"],"no_start_or_bootstrap")
        command=[{"project_id":P,"command":"start"}]
        self.assertEqual(classify(**snapshot(commands=command))["reason_code"],"start_without_bootstrap")

    def test_run_lifecycle(self):
        cases={"queued":("eligible","product_stage"),"running":("in_progress","worker_or_recovery"),
            "ci_pending":("waiting","ci"),"preview_ready":("waiting","preview"),
            "awaiting_release":("waiting","release"),"failed":("blocked","review_terminal_run")}
        for state,(expected,next_step) in cases.items():
            with self.subTest(state=state):
                actual=classify(**snapshot(status=state))
                self.assertEqual((actual["status"],actual["next_step"]),(expected,next_step))

    def test_cost_restrictions(self):
        for reason in ("paid_cost_unknown","budget_exhausted","cost_policy_or_ledger_unavailable"):
            cost={"state":"unknown" if reason.startswith("cost_policy") else "blocked","reason":reason}
            d=classify(**snapshot(status="queued",cost=cost))
            self.assertEqual((d["status"],d["reason_code"]),("blocked",reason))

    def test_actual_dispatch_contract(self):
        planned=[{"project_key":"demo"}]
        portfolio=[{"project_id":P}]
        d=classify(**snapshot(planned=planned,portfolio=portfolio))
        self.assertEqual((d["status"],d["next_step"]),("eligible","dispatch"))
        self.assertEqual(classify(**snapshot(planned=planned))["reason_code"],"portfolio_not_eligible")

    def test_cross_project_and_malformed_inventory_fail_closed(self):
        for changes in (
            {"tasks":[{"id":T,"project_id":OTHER}]},
            {"runs":[{"id":R,"task_id":OTHER,"status":"queued"}]},
            {"portfolio":[{"project_id":OTHER}]},
            {"commands":[{"project_id":OTHER,"command":"start"}]},
            {"control":{"project_id":OTHER,"state":"running"}},
            {"runs":[{"id":R,"task_id":T,"status":"mystery"}]},
        ):
            with self.subTest(changes=changes):
                kwargs=snapshot(status="queued");kwargs.update(changes)
                with self.assertRaises(RuntimeError):
                    classify(**kwargs)

    def test_reader_is_bounded_get_only_and_project_filtered(self):
        accessed=[]
        def get(path):
            accessed.append(path)
            if path.startswith("factory_projects?"):return [{"id":P,"project_key":"demo","is_active":True}]
            if path.startswith("factory_project_execution_controls?"):return [{"project_id":P,"state":"running"}]
            if path.startswith("factory_project_execution_commands?"):return []
            if path.startswith("factory_tasks?"):return []
            if path.startswith("rpc/factory_peek_planned_work"):return []
            if path.startswith("rpc/factory_portfolio_candidates"):return []
            raise AssertionError(path)
        policy=SimpleNamespace(read=lambda:SimpleNamespace(budget_usd=Decimal("10"),reserve_usd=Decimal("0.5")))
        health=SimpleNamespace(read=lambda **kw:SimpleNamespace(known_cost=Decimal("9.3010972"),unknown_cost_events=0))
        reader=SupabaseAdmissionReader(get=get,policy_reader=policy,health_reader=health)
        self.assertEqual(reader.read(project_key="demo")["reason_code"],"no_start_or_bootstrap")
        self.assertFalse(any("claim" in x or "dispatch" in x for x in accessed))
        with self.assertRaises(ValueError):reader.read(project_key="demo;drop")
        with self.assertRaises(ValueError):reader.read(project_key="demo",run_id="not-uuid")
        with self.assertRaises(RuntimeError):reader.read(project_key="demo",run_id=R)

    def test_unknown_cost_blocks_not_promotes(self):
        policy=SimpleNamespace(read=lambda:SimpleNamespace(budget_usd=Decimal("10"),reserve_usd=Decimal("0.5")))
        health=SimpleNamespace(read=lambda **kw:SimpleNamespace(known_cost=Decimal("1"),unknown_cost_events=1))
        reader=SupabaseAdmissionReader(get=lambda path:[],policy_reader=policy,health_reader=health)
        self.assertEqual(reader._cost()["reason"],"paid_cost_unknown")


if __name__=="__main__":
    unittest.main()
