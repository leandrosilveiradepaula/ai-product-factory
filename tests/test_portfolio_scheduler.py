import unittest
from unittest.mock import MagicMock

from ai_product_factory.portfolio_scheduler import SupabaseIncidentController,SupabasePortfolioScheduler


class PortfolioSchedulerTests(unittest.TestCase):
    def test_candidates_preserve_control_plane_order_and_soft_preemption(self):
        scheduler=SupabasePortfolioScheduler.__new__(SupabasePortfolioScheduler)
        scheduler._rpc=MagicMock(return_value=[
            {
                "project_id":"p1","project_key":"incident","priority":"P2","deadline":None,
                "customer_impact":5,"max_active_workers":4,"active_runs":1,
                "open_incident_severity":"P0","soft_preemption_active":True,
            },
            {
                "project_id":"p2","project_key":"normal","priority":"P1","deadline":"2026-09-30T12:00:00Z",
                "customer_impact":3,"max_active_workers":4,"active_runs":0,
                "open_incident_severity":None,"soft_preemption_active":True,
            },
        ])
        out=scheduler.candidates()
        self.assertEqual(out[0].project_key,"incident")
        self.assertEqual(out[0].open_incident_severity,"P0")
        self.assertTrue(out[0].soft_preemption_active)

    def test_selection_evidence_never_claims_worker_cancel_or_gate_bypass(self):
        scheduler=SupabasePortfolioScheduler.__new__(SupabasePortfolioScheduler)
        scheduler._rpc=MagicMock(side_effect=[
            [{
                "project_id":"p","project_key":"demo","priority":"P1","deadline":None,
                "customer_impact":4,"max_active_workers":3,"active_runs":1,
                "open_incident_severity":None,"soft_preemption_active":False,
            }],
            {"decision_id":1},
        ])
        selected=scheduler.select()
        self.assertEqual(selected.project_key,"demo")
        payload=scheduler._rpc.call_args_list[1].args[1]["p_reason"]
        self.assertFalse(payload["active_workers_cancelled"])
        self.assertFalse(payload["production_gates_bypassed"])

    def test_incident_controller_uses_durable_state_machine_rpcs(self):
        controller=SupabaseIncidentController.__new__(SupabaseIncidentController)
        controller._rpc=MagicMock(side_effect=[
            {"incident_id":"i","status":"triage","severity":"P0"},
            {"incident_id":"i","from":"triage","status":"investigating"},
        ])
        opened=controller.open(project_key="demo",severity="P0",title="Outage",summary="API down")
        moved=controller.transition(incident_id="i",status="investigating",evidence={"log_ref":"x"})
        self.assertEqual(opened["status"],"triage")
        self.assertEqual(moved["status"],"investigating")
        self.assertEqual(controller._rpc.call_args_list[0].args[0],"factory_open_incident")
        self.assertEqual(controller._rpc.call_args_list[1].args[0],"factory_transition_incident")


if __name__=="__main__":
    unittest.main()
