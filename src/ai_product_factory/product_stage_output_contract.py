from __future__ import annotations


class ProductStageOutputBlocked(ValueError):
    """A model response explicitly says that Product Stage was not executed."""


_BOOLEAN_NON_EXECUTION_MARKERS = frozenset(
    {
        "requires_model",
        "deferred",
        "placeholder",
        "mock",
        "fixture",
        "simulated",
        "dry_run",
    }
)
_STATUS_FIELDS = frozenset(
    {
        "mode",
        "execution_mode",
        "status",
        "execution_status",
        "result_status",
        "stage_status",
    }
)
_NON_EXECUTION_STATUSES = frozenset(
    {
        "placeholder",
        "mock",
        "fixture",
        "simulated",
        "simulation",
        "dry_run",
        "deferred",
        "requires_model",
    }
)


def _normalise(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _is_true_marker(value: object) -> bool:
    return value is True or _normalise(value) in {"true", "yes", "1"}


def assert_executed_product_stage_output(output: dict) -> None:
    """Reject explicit simulation/deferment markers before recording a stage.

    This deliberately evaluates only execution metadata at the response root.
    Product content may legitimately discuss fixtures, mocks, or simulations;
    such mentions do not turn a genuinely executed Product Stage into a mock.
    """
    if not isinstance(output, dict):
        raise ValueError("product stage output must be a mapping")

    for key in _BOOLEAN_NON_EXECUTION_MARKERS:
        if _is_true_marker(output.get(key)):
            raise ProductStageOutputBlocked("product_stage_output_not_executed")

    for key in _STATUS_FIELDS:
        if _normalise(output.get(key)) in _NON_EXECUTION_STATUSES:
            raise ProductStageOutputBlocked("product_stage_output_not_executed")
