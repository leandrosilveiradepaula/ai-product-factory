import unittest

from ai_product_factory.project_execution_control import (
    ControlTransitionDenied, ProjectCommand, ProjectControlSnapshot,
    ProjectExecutionState, can_claim_new_work, transition_control,
)


class ProjectExecutionControlTests(unittest.TestCase):
    def test_new_project_is_non_executable(self):
        first = ProjectControlSnapshot(ProjectExecutionState.DRAFT, 0, 0)
        self.assertFalse(can_claim_new_work(first.state))
        with self.assertRaises(ControlTransitionDenied):
            transition_control(first, ProjectCommand.RESUME, expected_version=0, actor_kind="operator")
        started = transition_control(first, ProjectCommand.START, expected_version=0, actor_kind="operator")
        self.assertEqual(started, ProjectControlSnapshot(ProjectExecutionState.RUNNING, 1, 1))
        self.assertTrue(can_claim_new_work(started.state))

    def test_pause_requires_verified_quiescence_before_paused(self):
        started = ProjectControlSnapshot(ProjectExecutionState.RUNNING, 1, 1)
        pausing = transition_control(started, ProjectCommand.PAUSE, expected_version=1, actor_kind="operator")
        self.assertFalse(can_claim_new_work(pausing.state))
        with self.assertRaises(ControlTransitionDenied):
            transition_control(pausing, ProjectCommand.CONFIRM_PAUSED, expected_version=2, actor_kind="operator",
                               acknowledged_quiescent=True)
        with self.assertRaises(ControlTransitionDenied):
            transition_control(pausing, ProjectCommand.CONFIRM_PAUSED, expected_version=2, actor_kind="controller")
        paused = transition_control(pausing, ProjectCommand.CONFIRM_PAUSED, expected_version=2,
                                    actor_kind="controller", acknowledged_quiescent=True)
        self.assertEqual(paused.state, ProjectExecutionState.PAUSED)
        resumed = transition_control(paused, ProjectCommand.RESUME, expected_version=3, actor_kind="operator")
        self.assertEqual(resumed.generation, 2)
        self.assertTrue(can_claim_new_work(resumed.state))

    def test_stop_and_restart_never_replay_lease_generation(self):
        snap = ProjectControlSnapshot(ProjectExecutionState.RUNNING, 1, 4)
        stopping = transition_control(snap, ProjectCommand.STOP, expected_version=1, actor_kind="operator")
        self.assertFalse(can_claim_new_work(stopping.state))
        stopped = transition_control(stopping, ProjectCommand.CONFIRM_STOPPED,
                                     expected_version=2, actor_kind="controller", acknowledged_quiescent=True)
        self.assertEqual(stopped.state, ProjectExecutionState.STOPPED)
        restarted = transition_control(stopped, ProjectCommand.RESTART, expected_version=3, actor_kind="operator")
        self.assertEqual(restarted.generation, 5)
        self.assertNotEqual(restarted.generation, snap.generation)

    def test_stale_or_unauthenticated_commands_denied(self):
        snap = ProjectControlSnapshot(ProjectExecutionState.RUNNING, 4, 9)
        for command, version, actor in [
            (ProjectCommand.PAUSE, 3, "operator"),
            (ProjectCommand.PAUSE, 4, "scheduler"),
            (ProjectCommand.START, 4, "operator"),
            (ProjectCommand.RESTART, 4, "operator"),
        ]:
            with self.subTest(command=command, actor=actor):
                with self.assertRaises(ControlTransitionDenied):
                    transition_control(snap, command, expected_version=version, actor_kind=actor)

    def test_unknown_state_fails_closed(self):
        for value in ("running ", "RUNNING", "", None, "paused", "stopped"):
            self.assertFalse(can_claim_new_work(value))
        for state in ProjectExecutionState:
            self.assertEqual(can_claim_new_work(state), state == ProjectExecutionState.RUNNING)

    def test_snapshot_rejects_unknown_or_untyped_states(self):
        for state in ("running", "RUNNING", "", None, True):
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    ProjectControlSnapshot(state, 1, 1)

    def test_every_nonrunning_state_denies_claim(self):
        for state in ProjectExecutionState:
            self.assertEqual(can_claim_new_work(state),state is ProjectExecutionState.RUNNING)

    def test_invalid_snapshot_is_denied(self):
        for version, gen in ((-1, 0), (0, -1), (True, 0)):
            with self.assertRaises(ValueError):
                ProjectControlSnapshot(ProjectExecutionState.DRAFT, version, gen)


if __name__ == "__main__":
    unittest.main()
