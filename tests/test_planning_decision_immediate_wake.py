"""Regression: a valid human planning answer must wake its queued run now.

The runner still independently verifies provider budget, project state and
cost. GitHub dispatch acceptance is not an executed Product Stage receipt.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = (ROOT / "apps/console/lib/control-plane.ts").read_text()
WAKE = (ROOT / "apps/console/lib/planning-decision-wake.ts").read_text()
PAGE = (ROOT / "apps/console/app/gates/page.tsx").read_text()
DISPATCH = (ROOT / "apps/console/lib/intake-worker-wake.ts").read_text()


class PlanningDecisionImmediateWakeTests(unittest.TestCase):
    def test_successful_planning_gate_queues_then_wakes_once(self):
        handler = CONTROL.split("export async function resolveHumanGate(", 1)[1].split(
            "export type OperatorAdminRow", 1
        )[0]
        self.assertIn('const receipt=await response.json();', handler)
        self.assertIn(
            'gate.gate_type==="planning_decision"&&resolution==="approved"', handler
        )
        self.assertIn("await wakeApprovedPlanningDecision(gateId,receipt)", handler)
        self.assertLess(
            handler.index('if(!response.ok)throw new Error("Unable to resolve human gate")'),
            handler.index("await wakeApprovedPlanningDecision(gateId,receipt)"),
        )
        self.assertIn("return {...receipt,wakeStatus};", handler)
        self.assertNotIn("requestIntakeWorkerWake()", handler.split(
            'gate.gate_type==="planning_decision"&&resolution==="approved"', 1
        )[0].split('if(v2){',1)[0])

    def test_only_exact_approved_continuation_and_running_project_can_dispatch(self):
        for contract in (
            'receipt.gate_id!==gateId',
            'receipt.resolution!=="approved"',
            "UUID.test(String(receipt.resume_task_id",
            "UUID.test(String(receipt.resume_run_id",
            '"planning_replan_queued","planning_reconciliation_queued"',
            "QUEUED_PLANNING_STATES.has",
            "getSupabaseServerConfig()",
            '/rest/v1/factory_tasks?select=id,project_id',
            "rows.length!==1",
            'rows[0]?.id!==receipt.resume_task_id',
            "/rest/v1/factory_project_execution_controls",
            "controls.length!==1",
            'controls[0]?.state!=="running"',
            'return "not_needed"',
            "status=await requestIntakeWorkerWake()",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, WAKE)
        self.assertLess(WAKE.index("controls[0]?.state"), WAKE.index(
            "status=await requestIntakeWorkerWake()"
        ))

    def test_result_is_audit_not_worker_execution(self):
        for item in (
            "project.continuation.wake_attempted",
            "task_id:receipt.resume_task_id",
            "run_id:receipt.resume_run_id",
            "project_id:projectId",
            "gate_id:gateId",
            'source:"planning-decision"',
            'execution_state:"running"',
            "if(!audit.ok)console.warn",
        ):
            with self.subTest(item=item):
                self.assertIn(item, WAKE)
        self.assertIn("GitHub returns only dispatch acceptance", WAKE)
        self.assertIn("does NOT prove execution", WAKE)
        self.assertIn("project.continuation.wake_attempted", CONTROL)

    def test_ui_reports_observed_wake_truthfully(self):
        self.assertIn("planningWakeStatus", PAGE)
        self.assertIn("if(planningWakeStatus)redirect(", PAGE)
        self.assertIn('role="status"', PAGE)
        self.assertIn("Isso ainda não comprova que o worker iniciou.", PAGE)
        self.assertIn("A fila permanece preservada.", PAGE)
        self.assertIn('if(gateType==="planning_decision"&&resolution==="approved")', PAGE)
        self.assertIn("repository_dispatch", DISPATCH) if "repository_dispatch" in DISPATCH else self.assertIn(
            "requestFactoryIntakeWakeViaGitHubApp", DISPATCH
        )

    def test_never_bypasses_production_paid_or_operator_gates(self):
        for unsafe in (
            "merge_pull_request", "auto_merge", "OPENAI_API_KEY",
            "service_role", "NEXT_PUBLIC_", "factory_control_project_v1",
            "factory_enqueue_project_bootstrap", "factory_claim_product_run",
        ):
            with self.subTest(unsafe=unsafe):
                self.assertNotIn(unsafe, WAKE)
        self.assertIn("requireConsoleOperator()", CONTROL)
        self.assertIn("getSupabaseServerConfig()", WAKE)


if __name__ == "__main__":
    unittest.main()
