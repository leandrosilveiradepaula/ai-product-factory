import unittest

from ai_product_factory.model_executor import (
    ModelBudget,
    ModelExecutor,
    ModelRequest,
    ModelResult,
    ModelRole,
)
from ai_product_factory.models import ExecutionRoute


class FakeProvider:
    def __init__(self, role):
        self.role = role
        self.requests = []
    def execute(self, request):
        self.requests.append(request)
        return ModelResult(self.role, "ok", provider_ref="fake")


class ModelExecutorTests(unittest.TestCase):
    def test_direct_route_uses_primary(self):
        primary = FakeProvider(ModelRole.PRIMARY)
        codex = FakeProvider(ModelRole.CODEX)
        executor = ModelExecutor(primary=primary, codex=codex)
        result = executor.execute(
            ExecutionRoute.DIRECT,
            ModelRequest(task_id="t1", objective="implement", context="ctx"),
        )
        self.assertEqual(result.role, ModelRole.PRIMARY)
        self.assertEqual(len(primary.requests), 1)
        self.assertEqual(len(codex.requests), 0)

    def test_codex_route_is_explicit(self):
        primary = FakeProvider(ModelRole.PRIMARY)
        codex = FakeProvider(ModelRole.CODEX)
        executor = ModelExecutor(primary=primary, codex=codex)
        result = executor.execute(
            ExecutionRoute.CODEX,
            ModelRequest(task_id="t1", objective="deep refactor", context="ctx"),
        )
        self.assertEqual(result.role, ModelRole.CODEX)
        self.assertEqual(len(codex.requests), 1)

    def test_codex_budget_defaults_to_one(self):
        executor = ModelExecutor(
            primary=FakeProvider(ModelRole.PRIMARY),
            codex=FakeProvider(ModelRole.CODEX),
        )
        request = ModelRequest(task_id="t1", objective="x", context="ctx")
        executor.execute(ExecutionRoute.CODEX, request)
        with self.assertRaises(RuntimeError):
            executor.execute(ExecutionRoute.CODEX, request)

    def test_primary_budget_is_bounded(self):
        executor = ModelExecutor(
            primary=FakeProvider(ModelRole.PRIMARY),
            budget=ModelBudget(max_primary_calls_per_task=1),
        )
        request = ModelRequest(task_id="t1", objective="x", context="ctx")
        executor.execute(ExecutionRoute.DIRECT, request)
        with self.assertRaises(RuntimeError):
            executor.execute(ExecutionRoute.DIRECT, request)

    def test_missing_codex_provider_fails_closed(self):
        executor = ModelExecutor(primary=FakeProvider(ModelRole.PRIMARY), codex=None)
        with self.assertRaises(RuntimeError):
            executor.execute(
                ExecutionRoute.CODEX,
                ModelRequest(task_id="t1", objective="x", context="ctx"),
            )


if __name__ == "__main__":
    unittest.main()
