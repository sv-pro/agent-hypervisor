"""
agent_hypervisor.economic — Economic constraint enforcement.

Economic constraints are a first-class enforcement dimension, alongside
capability constraints (what can be done) and provenance/taint constraints
(where data comes from).  They answer a third question:

    What is this agent allowed to spend?

This package contains four components:

    PricingRegistry      — static model/tool pricing table (compiled at startup)
    CostEstimator        — pre-execution cost estimation
    EconomicPolicyEngine — budget evaluation and REPLAN verdict generation
    CostProfileStore     — trace-driven empirical cost profiles (Phase 3+)

The enforcement contract:

    CostEstimator.estimate_cost(...)  →  CostEstimate (float, conservative)
    EconomicPolicyEngine.evaluate_budget(estimate, budget)
        →  allow   if estimate ≤ budget
        →  replan  if estimate > budget AND cheaper path exists
        →  deny    if estimate > budget AND no cheaper path exists

No LLM participates in this path.  The pricing table and budget limits are
compiled artifacts — they are frozen at startup, not re-read from YAML at
enforcement time.

See docs/architecture/economic_constraints.md for the full specification.
"""

from .cost_estimator import CostEstimate, CostEstimator
from .economic_policy import EconomicPolicyEngine, ReplanHint
from .pricing_registry import ModelPricing, PricingRegistry

__all__ = [
    "CostEstimate",
    "CostEstimator",
    "EconomicPolicyEngine",
    "ModelPricing",
    "PricingRegistry",
    "ReplanHint",
]
