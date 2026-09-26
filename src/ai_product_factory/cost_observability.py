from __future__ import annotations

PAID_TOOL_FAMILIES=frozenset({"model","openai","llm","paid_provider"})

def requires_cost_estimate(tool_family:str|None)->bool:
    return str(tool_family or "").strip().lower() in PAID_TOOL_FAMILIES
