from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class CostCeilingDecision:
 allowed:bool
 reason:str
 remaining:Decimal|None

def evaluate_cost_ceiling(*,budget:Decimal|None,known_spend:Decimal,reserved_cost:Decimal|None,strict:bool=True)->CostCeilingDecision:
 if known_spend<0:raise ValueError("known spend cannot be negative")
 if budget is None:return CostCeilingDecision(not strict,"budget is not configured",None)
 remaining=budget-known_spend
 if remaining<0:return CostCeilingDecision(False,"known spend already exceeds budget",remaining)
 if reserved_cost is None:return CostCeilingDecision(not strict,"provider cost reservation is unknown",remaining)
 if reserved_cost<0:raise ValueError("reserved cost cannot be negative")
 if reserved_cost>remaining:return CostCeilingDecision(False,"reserved provider cost exceeds remaining budget",remaining)
 return CostCeilingDecision(True,"within budget",remaining-reserved_cost)

def require_cost_ceiling(**kwargs)->CostCeilingDecision:
 decision=evaluate_cost_ceiling(**kwargs)
 if not decision.allowed:raise PermissionError(decision.reason)
 return decision
