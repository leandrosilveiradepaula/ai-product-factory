import unittest

from ai_product_factory.models import LifecycleStage, ProjectState
from ai_product_factory.state_machine import InvalidTransition, transition


class StateMachineTests(unittest.TestCase):
    def test_happy_path(self):
        state = ProjectState(project_key="demo")
        for stage in (
            LifecycleStage.SPECIFICATION,
            LifecycleStage.PLANNING,
            LifecycleStage.IMPLEMENTATION,
            LifecycleStage.REVIEW,
            LifecycleStage.VALIDATION,
            LifecycleStage.PREVIEW,
            LifecycleStage.HUMAN_GATE,
            LifecycleStage.RELEASE,
            LifecycleStage.OPERATIONS,
        ):
            transition(state, stage)
        self.assertEqual(state.stage, LifecycleStage.OPERATIONS)

    def test_validation_can_return_to_implementation(self):
        state = ProjectState(project_key="demo", stage=LifecycleStage.VALIDATION)
        transition(state, LifecycleStage.IMPLEMENTATION)
        self.assertEqual(state.stage, LifecycleStage.IMPLEMENTATION)

    def test_invalid_jump_is_rejected(self):
        state = ProjectState(project_key="demo")
        with self.assertRaises(InvalidTransition):
            transition(state, LifecycleStage.RELEASE)


if __name__ == "__main__":
    unittest.main()
