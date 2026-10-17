"""Console manual execution controls: fail-closed UX and wake contracts.

Static code contracts complement the isolated PostgreSQL lifecycle regression
and Next.js typecheck; tests do not send commands or start any projects.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTROL = (ROOT / "apps/console/lib/control-plane.ts").read_text()
PAGE = (ROOT / "apps/console/app/projects/[key]/page.tsx").read_text()
CONFIRM = (ROOT / "apps/console/app/projects/[key]/control-confirm.tsx").read_text()
WAKE = (ROOT / "apps/console/lib/intake-worker-wake.ts").read_text()
RUNNER = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()


class ManualProjectControlConsoleContract(unittest.TestCase):
    def test_invalid_control_rows_fail_closed_before_rendering_controls(self):
        for marker in (
            "projectControlStates=new Set",
            'state:"unavailable",version:-1,generation:0',
            'typeof state!=="string"||!projectControlStates.has(state)',
            "!Number.isSafeInteger(version)||version<0",
            "!Number.isSafeInteger(generation)||generation<0",
            'state==="draft"&&generation!==0',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, CONTROL)
        self.assertIn('executionControl.state==="unavailable"', PAGE)
        self.assertIn("Nenhum comando foi liberado", PAGE)

    def test_stop_is_available_during_pausing_without_enabling_resume(self):
        self.assertIn('["pausing","stop","Parar"]', PAGE)
        self.assertIn('["running","stop","Parar"]', PAGE)
        self.assertIn('["paused","stop","Parar"]', PAGE)
        self.assertNotIn('["pausing","resume","Retomar"]', PAGE)
        self.assertNotIn('["stopping","restart","Reiniciar"]', PAGE)

    def test_manual_transitions_signal_scheduler_only_after_rpc_succeeds(self):
        command = CONTROL.split("export async function commandProjectExecution(", 1)[1].split(
            "\nexport async function enqueueProjectBootstrap", 1)[0]
        self.assertLess(command.index("if(!response.ok)throw"), command.index("const shouldWake="))
        self.assertLess(command.index("const shouldWake="), command.index("requestIntakeWorkerWake()"))
        self.assertIn('result.state==="running"&&["start","resume","restart"].includes(command)', command)
        self.assertIn('["pausing","stopping"].includes(result.state)', command)
        self.assertIn('wakeStatus:"requested"|"failed"|"unconfigured"|"not_needed"', command)
        self.assertIn("catch{wakeStatus=\"failed\"", command)
        self.assertNotIn('result.run_id', command)
        self.assertNotIn("FACTORY_PRIMARY_MODEL_ENABLED", command)

    def test_wake_is_best_effort_and_does_not_bypass_guards(self):
        self.assertIn('if(wakeStatus!=="requested")', CONTROL)
        self.assertIn('return {state:result.state', CONTROL)
        self.assertIn("requestFactoryIntakeWakeViaGitHubApp", WAKE)
        self.assertIn('github.event.client_payload.source == \'console-intake\'', RUNNER)
        self.assertIn("--mode project-control-settle", RUNNER)
        self.assertNotIn("merge_pull_request", CONTROL + WAKE)

    def test_operator_receives_truthful_durable_acknowledgement(self):
        self.assertIn('redirect("/projects/"+key+"?control="+notice)', PAGE)
        self.assertIn('result.wakeStatus==="requested"', PAGE)
        self.assertIn('result.wakeStatus==="not_needed"', PAGE)
        for value in ("requested", "delayed", "recorded"):
            self.assertIn(value + ":{status:", PAGE)
        self.assertIn("Comando salvo, mas não foi possível solicitar", PAGE)
        self.assertIn("Nenhuma nova execução foi iniciada por esta confirmação", PAGE)

    def test_action_card_uses_actual_execution_state_not_lifecycle_stage(self):
        self.assertIn("controlNextAction(executionControl.state)", PAGE)
        self.assertIn("const action=focusedControlAction|| (observedBlocker?", PAGE)
        self.assertIn('id="project-control"', PAGE)
        for title in (
            "Projeto cadastrado, aguardando seu início",
            "Projeto pausado por você",
            "Projeto parado por você",
            "Pausa sendo concluída",
            "Parada sendo concluída",
            "Controle de execução indisponível",
        ):
            self.assertIn(title, PAGE)
        self.assertIn('executionControl.state==="running"?<ActionLink', PAGE)
        self.assertIn('p.kind==="existing"&&executionControl.state==="running"', PAGE)

    def test_stop_confirmation_explains_graceful_drain(self):
        for content in (
            "Nenhuma tarefa nova será assumida",
            "Trabalhos já assumidos poderão concluir com segurança",
            "fila e o histórico serão preservados",
            'command==="restart"',
        ):
            self.assertIn(content, CONFIRM)
        self.assertIn('const destructive=command==="stop";', CONFIRM)

    def test_registration_remains_non_executable(self):
        registration = CONTROL.split("export async function createProjectIntakeAndBootstrap(", 1)[1].split(
            "export type ProjectExecutionControl", 1)[0]
        self.assertNotIn("requestIntakeWorkerWake()", registration)
        self.assertIn("rpc/factory_register_project_intake_v2", registration)


if __name__ == "__main__":
    unittest.main()
