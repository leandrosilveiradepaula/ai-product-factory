from __future__ import annotations

import json
import re


class ProductStageOutputBlocked(ValueError):
    """A model response explicitly says that Product Stage was not executed."""


NON_ACTIONABLE_PLANNING_EVIDENCE = {
    "reason_code": "planning_non_actionable",
    "observed_model_response": True,
    "tasks_count": 0,
    "decisions_count": 0,
    "implementation_completed": False,
    "requires_scope_reconciliation": True,
}


class PlanningNoActionableWork(ValueError):
    """A real planning model returned no executable task or decision."""

    def __init__(self) -> None:
        super().__init__("planning has no actionable tasks or decisions")


_BOOLEAN_NON_EXECUTION_MARKERS = frozenset(
    {
        "requires_model",
        "deferred",
        "placeholder",
        "mock",
        "fixture",
        "simulated",
        "dry_run",
        "noop",
        "no_op",
        "demo",
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
        "noop",
        "no_op",
        "demo",
        "not_executed",
        "skipped",
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
    Product content may legitimately discuss fixtures, mocks, demos or simulations;
    such mentions do not turn a genuinely executed Product Stage into a mock.
    But execution metadata saying noop/no-op/demo/skipped/not_executed is never
    evidence of a completed stage or authority for a release.
    """
    if not isinstance(output, dict):
        raise ValueError("product stage output must be a mapping")

    for key in _BOOLEAN_NON_EXECUTION_MARKERS:
        if _is_true_marker(output.get(key)):
            raise ProductStageOutputBlocked("product_stage_output_not_executed")

    for key in _STATUS_FIELDS:
        if _normalise(output.get(key)) in _NON_EXECUTION_STATUSES:
            raise ProductStageOutputBlocked("product_stage_output_not_executed")


class ProductStageOutputTruncated(ValueError):
    """A provider explicitly truncated output or malformed JSON hit its cap."""

    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"{stage} output truncated at provider limit")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError("non-finite JSON value")


def decode_product_stage_object(result, stage: str) -> dict:
    """Parse exactly one complete JSON object, optionally in one JSON fence.

    Never reconstruct missing braces, accept a partial object, select a JSON
    substring from prose, or persist the rejected provider response.
    """
    if result.output_truncated:
        raise ProductStageOutputTruncated(stage)
    try:
        if not isinstance(result.output, str):
            raise ValueError("non-text output")
        text = result.output.strip()
        fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```[ \t]*",
                              text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1)
        output = json.loads(text, object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
    except (ValueError, TypeError, RecursionError):
        if result.output_limit_reached:
            raise ProductStageOutputTruncated(stage) from None
        raise ValueError(f"{stage} returned invalid JSON") from None
    if not isinstance(output, dict):
        raise ValueError(f"{stage} output must be a JSON object")
    return output
