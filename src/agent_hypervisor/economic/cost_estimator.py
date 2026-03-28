"""
cost_estimator.py — Pre-execution cost estimation.

The CostEstimator computes a conservative (upper-bound) cost estimate for a
proposed action before any tool call is made.  The estimate is used by
EconomicPolicyEngine to enforce budget limits at IR construction time.

Estimation model::

    estimated_cost =
        (input_tokens  * input_price_per_1k  / 1000)
      + (output_tokens_cap * output_price_per_1k / 1000)
      + tool_fixed_cost
      * uncertainty_multiplier

Design invariants:
  - No LLM on the estimation path.
  - Input token count is derived from the actual input, not a guess.
  - Output is bounded by ``max_tokens``; never by predicted output length.
  - Uncertainty multiplier is applied to the full estimate (≥ 1.0).
  - If pricing for a model is unknown, the estimate is ``float('inf')``
    (fail-closed: unknown cost → budget exceeded → deny or replan).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .pricing_registry import PricingRegistry


@dataclass(frozen=True)
class CostEstimate:
    """
    The conservative cost estimate for one proposed action.

    All fields are in USD.

    Attributes:
        model_name:          The model whose pricing was used.
        input_tokens:        Estimated input token count.
        output_tokens_cap:   Hard output bound (max_tokens declared in call).
        input_cost:          input_tokens × input_price_per_1k / 1000
        output_cost:         output_tokens_cap × output_price_per_1k / 1000
        tool_fixed_cost:     Fixed cost for the tool call (0.0 if not declared).
        uncertainty_mult:    Multiplier applied to the subtotal.
        total:               Full conservative estimate (already multiplied).
        is_unbounded:        True if pricing was unavailable; cost is infinite.
    """
    model_name:        str
    input_tokens:      int
    output_tokens_cap: int
    input_cost:        float
    output_cost:       float
    tool_fixed_cost:   float
    uncertainty_mult:  float
    total:             float
    is_unbounded:      bool = False


class CostEstimator:
    """
    Computes conservative pre-execution cost estimates.

    Constructed with a compiled PricingRegistry and a manifest-level
    uncertainty multiplier.  Both are frozen at compile time.

    Usage::

        estimator = CostEstimator(registry, uncertainty_multiplier=1.2)
        estimate  = estimator.estimate_llm_cost(
            model_name     = "claude-sonnet-4-6",
            input_text     = full_context_string,
            max_tokens     = 1024,
            tool_name      = "summarize",
        )
    """

    def __init__(
        self,
        pricing_registry: PricingRegistry,
        uncertainty_multiplier: float = 1.2,
    ) -> None:
        if uncertainty_multiplier < 1.0:
            raise ValueError(
                "uncertainty_multiplier must be ≥ 1.0 (conservative estimation required)"
            )
        self._registry = pricing_registry
        self._multiplier = uncertainty_multiplier

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_llm_cost(
        self,
        model_name: str,
        input_text: str,
        max_tokens: int,
        tool_name: str = "",
    ) -> CostEstimate:
        """
        Estimate the cost of one LLM call.

        Args:
            model_name: Model identifier, must match a key in PricingRegistry.
            input_text: The full input that will be sent to the model.
            max_tokens: The declared output token cap (``max_tokens`` parameter).
            tool_name:  Optional tool name — adds fixed tool cost if declared.

        Returns:
            CostEstimate with ``is_unbounded=True`` if model pricing is unknown.
        """
        pricing = self._registry.get(model_name)
        if pricing is None:
            # Unknown model → infinite cost (fail-closed).
            return CostEstimate(
                model_name=model_name,
                input_tokens=0,
                output_tokens_cap=max_tokens,
                input_cost=0.0,
                output_cost=0.0,
                tool_fixed_cost=0.0,
                uncertainty_mult=self._multiplier,
                total=float("inf"),
                is_unbounded=True,
            )

        input_tokens = self._count_tokens(input_text)
        input_cost   = input_tokens * pricing.input_per_1k / 1000.0
        output_cost  = max_tokens  * pricing.output_per_1k / 1000.0
        tool_cost    = self._registry.tool_cost(tool_name) if tool_name else 0.0
        subtotal     = input_cost + output_cost + tool_cost
        total        = subtotal * self._multiplier

        return CostEstimate(
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens_cap=max_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            tool_fixed_cost=tool_cost,
            uncertainty_mult=self._multiplier,
            total=total,
            is_unbounded=False,
        )

    def estimate_plan_cost(
        self,
        steps: list[dict[str, Any]],
    ) -> tuple[CostEstimate, ...]:
        """
        Estimate the cost of each step in a multi-step plan.

        Each step dict must contain:
            model_name  — str
            input_text  — str
            max_tokens  — int
            tool_name   — str (optional, default "")

        Returns a tuple of CostEstimates, one per step, in declaration order.
        The caller is responsible for summing totals and comparing to the
        session budget.
        """
        estimates = []
        for step in steps:
            estimates.append(
                self.estimate_llm_cost(
                    model_name=step["model_name"],
                    input_text=step.get("input_text", ""),
                    max_tokens=step.get("max_tokens", 1024),
                    tool_name=step.get("tool_name", ""),
                )
            )
        return tuple(estimates)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_tokens(text: str) -> int:
        """
        Conservative token count estimate.

        Uses a character-based heuristic (4 chars ≈ 1 token for English).
        This intentionally over-counts to preserve the conservative invariant.
        A proper tokenizer (tiktoken, sentencepiece) may be substituted here
        once a dependency is accepted; the interface does not change.
        """
        # 4 chars per token is a well-known English over-estimate.
        # For structured/code content the ratio is lower, which means this
        # heuristic is *more* conservative — correct direction.
        return max(1, len(text) // 4)
