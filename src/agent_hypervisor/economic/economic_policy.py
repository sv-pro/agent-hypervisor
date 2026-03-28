"""
economic_policy.py — Budget evaluation and REPLAN verdict generation.

The EconomicPolicyEngine is the enforcement surface for economic constraints.
It is consulted at IR construction time, after capability and provenance checks.

Verdict contract::

    evaluate_budget(estimate, budget_limit)
        →  "allow"   — estimate ≤ budget_limit
        →  "replan"  — estimate > budget_limit, cheaper path structurally exists
        →  "deny"    — estimate > budget_limit, no cheaper path available

A "replan" verdict carries a ReplanHint: a deterministic, structured suggestion
computed entirely from compiled artifacts.  No LLM is consulted.

Design invariants:
  - Same inputs always produce the same verdict (deterministic).
  - The engine never modifies budgets, manifests, or pricing tables.
  - BudgetExceeded is raised (not returned) when the verdict is deny or replan,
    matching the ConstructionError contract of the IRBuilder.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..runtime.models import BudgetExceeded
from .cost_estimator import CostEstimate
from .pricing_registry import PricingRegistry


@dataclass(frozen=True)
class ReplanHint:
    """
    A deterministic, structured suggestion for a cheaper execution path.

    Produced by EconomicPolicyEngine when a REPLAN verdict is issued.
    All fields are derived from compiled artifacts; no LLM is involved.

    Attributes:
        reason:              Why the original plan exceeded the budget.
        switch_model:        Cheaper model name from PricingRegistry, if any.
        reduce_max_tokens:   Suggested output cap (None if already minimal).
        truncate_context:    Suggested input token ceiling (None if not applicable).
        split_into_subtasks: True when task decomposition is the advised strategy.
    """
    reason:              str
    switch_model:        str | None = None
    reduce_max_tokens:   int | None = None
    truncate_context:    int | None = None
    split_into_subtasks: bool = False


@dataclass(frozen=True)
class CompiledBudget:
    """
    Compiled budget limits for one scope.

    Populated from the world manifest ``economic.budgets`` section
    at compile time.  Immutable thereafter.
    """
    per_request: float   # USD — ceiling per single intent evaluation
    per_session: float   # USD — cumulative ceiling for the session


class EconomicPolicyEngine:
    """
    Enforces economic constraints at IR construction time.

    Constructed from compiled artifacts at startup.  All enforcement calls
    operate on frozen data; no YAML is accessed at runtime.

    Args:
        budget:           Compiled per-request and per-session limits.
        pricing_registry: Frozen model/tool pricing table.
        session_spent:    Running total of actual cost for the current session.
                          Updated externally (by the trace recorder) after each
                          successful execution.
    """

    def __init__(
        self,
        budget: CompiledBudget,
        pricing_registry: PricingRegistry,
        session_spent: float = 0.0,
    ) -> None:
        self._budget = budget
        self._registry = pricing_registry
        self._session_spent = session_spent

    # ------------------------------------------------------------------
    # External update (called by trace recorder after execution)
    # ------------------------------------------------------------------

    def record_actual_cost(self, actual_cost: float) -> None:
        """
        Accumulate actual cost after a successful execution.

        Called by the trace recorder once the LLM/tool response is received
        and real token counts are known.  The session accumulator is the
        only mutable state in this engine.
        """
        self._session_spent += actual_cost

    # ------------------------------------------------------------------
    # Enforcement-time evaluation
    # ------------------------------------------------------------------

    def evaluate_budget(
        self,
        estimate: CostEstimate,
        request_budget_override: float | None = None,
    ) -> None:
        """
        Enforce budget limits for one proposed action.

        Raises ``BudgetExceeded`` if the estimate exceeds the applicable
        budget.  Returns silently if the estimate is within budget.

        Args:
            estimate:                CostEstimate from CostEstimator.
            request_budget_override: Per-policy budget override from a matched
                                     economic policy rule, if any.

        Raises:
            BudgetExceeded: estimate > applicable limit.
                            ``.replan_hint`` is set if a cheaper path exists,
                            None otherwise.
        """
        per_request_limit = (
            request_budget_override
            if request_budget_override is not None
            else self._budget.per_request
        )
        remaining_session = self._budget.per_session - self._session_spent

        # Determine binding limit (most restrictive wins).
        binding_limit = min(per_request_limit, remaining_session)

        if estimate.total <= binding_limit:
            return  # within budget — allow

        # Over budget: attempt to produce a REPLAN hint.
        hint = self._build_replan_hint(estimate, binding_limit)

        raise BudgetExceeded(
            reason=(
                f"Estimated cost ${estimate.total:.4f} exceeds budget "
                f"${binding_limit:.4f} "
                f"(per_request=${per_request_limit:.4f}, "
                f"session_remaining=${remaining_session:.4f})"
            ),
            estimated_cost=estimate.total,
            budget_limit=binding_limit,
            replan_hint=hint,
        )

    # ------------------------------------------------------------------
    # Internal: replan hint construction
    # ------------------------------------------------------------------

    def _build_replan_hint(
        self,
        estimate: CostEstimate,
        budget_limit: float,
    ) -> ReplanHint | None:
        """
        Build a deterministic REPLAN hint, or return None if no cheaper
        path is structurally available.

        Strategy (in order):
        1. If a cheaper model exists in the registry, suggest switching.
        2. If output cap reduction would bring cost within budget, suggest it.
        3. If input truncation would help, suggest a token ceiling.
        4. If none of the above suffice, suggest task decomposition.
        5. If the cheapest possible estimate still exceeds the limit, return
           None (no replan available → verdict becomes DENY).
        """
        # Strategy 1: cheaper model
        cheapest = self._registry.cheapest_model()
        if cheapest and cheapest.model_name != estimate.model_name:
            # Check whether switching alone would suffice.
            cheaper_input_cost  = estimate.input_tokens * cheapest.input_per_1k / 1000.0
            cheaper_output_cost = estimate.output_tokens_cap * cheapest.output_per_1k / 1000.0
            cheaper_total = (cheaper_input_cost + cheaper_output_cost) * estimate.uncertainty_mult
            if cheaper_total <= budget_limit:
                return ReplanHint(
                    reason=(
                        f"Model {estimate.model_name!r} estimated at "
                        f"${estimate.total:.4f}; switching to "
                        f"{cheapest.model_name!r} gives ${cheaper_total:.4f}"
                    ),
                    switch_model=cheapest.model_name,
                )

        # Strategy 2: reduce max_tokens cap
        if estimate.output_tokens_cap > 256:
            pricing = self._registry.get(estimate.model_name)
            if pricing:
                reduced_cap = estimate.output_tokens_cap // 2
                reduced_output_cost = reduced_cap * pricing.output_per_1k / 1000.0
                reduced_total = (
                    estimate.input_cost + reduced_output_cost + estimate.tool_fixed_cost
                ) * estimate.uncertainty_mult
                if reduced_total <= budget_limit:
                    return ReplanHint(
                        reason=(
                            f"Reducing max_tokens from {estimate.output_tokens_cap} "
                            f"to {reduced_cap} brings estimate to ${reduced_total:.4f}"
                        ),
                        reduce_max_tokens=reduced_cap,
                    )

        # Strategy 3: truncate input context
        pricing = self._registry.get(estimate.model_name)
        if pricing and estimate.input_tokens > 512:
            target_tokens = estimate.input_tokens // 2
            truncated_input_cost  = target_tokens * pricing.input_per_1k / 1000.0
            truncated_total = (
                truncated_input_cost + estimate.output_cost + estimate.tool_fixed_cost
            ) * estimate.uncertainty_mult
            if truncated_total <= budget_limit:
                return ReplanHint(
                    reason=(
                        f"Truncating context from {estimate.input_tokens} to "
                        f"{target_tokens} tokens brings estimate to ${truncated_total:.4f}"
                    ),
                    truncate_context=target_tokens,
                )

        # Strategy 4: suggest decomposition (always structurally available)
        return ReplanHint(
            reason=(
                f"No single-call cheaper path found for budget ${budget_limit:.4f}. "
                "Consider decomposing the task into smaller sub-calls."
            ),
            split_into_subtasks=True,
        )
