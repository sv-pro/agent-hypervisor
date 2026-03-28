"""
pricing_registry.py — Static model and tool pricing table.

The PricingRegistry is a compiled artifact: it is populated once at startup
from the world manifest's ``economic.model_pricing`` section and never
re-read from YAML at enforcement time.

All prices are expressed in USD.

Usage (compile time — called from compile_world()):

    registry = PricingRegistry.from_manifest(manifest_economic_section)

Usage (enforcement time):

    pricing = registry.get("claude-sonnet-4-6")
    # pricing.input_per_1k, pricing.output_per_1k
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ModelPricing:
    """
    Compiled pricing for one model.

    input_per_1k  — USD cost per 1 000 input tokens
    output_per_1k — USD cost per 1 000 output tokens
    """
    model_name:    str
    input_per_1k:  float
    output_per_1k: float

    def __post_init__(self) -> None:
        if self.input_per_1k < 0 or self.output_per_1k < 0:
            raise ValueError(
                f"ModelPricing for {self.model_name!r}: prices must be non-negative"
            )


class PricingRegistry:
    """
    Frozen registry of model and tool pricing.

    Constructed once at compile time; immutable thereafter.
    ``get()`` is the only access path at enforcement time.
    """

    def __init__(
        self,
        model_pricing: dict[str, ModelPricing],
        tool_costs: dict[str, float] | None = None,
    ) -> None:
        self._models: MappingProxyType[str, ModelPricing] = MappingProxyType(
            dict(model_pricing)
        )
        self._tools: MappingProxyType[str, float] = MappingProxyType(
            dict(tool_costs or {})
        )

    # ------------------------------------------------------------------
    # Compile-time factory
    # ------------------------------------------------------------------

    @classmethod
    def from_manifest(cls, economic_section: dict[str, Any]) -> "PricingRegistry":
        """
        Construct a PricingRegistry from the ``economic`` block of a world manifest.

        Expected shape::

            model_pricing:
              <model_name>:
                input_per_1k:  float
                output_per_1k: float

        Missing fields raise ``ValueError`` at compile time, never at runtime.
        """
        raw_pricing: dict[str, Any] = economic_section.get("model_pricing", {})
        models: dict[str, ModelPricing] = {}
        for name, spec in raw_pricing.items():
            models[name] = ModelPricing(
                model_name=name,
                input_per_1k=float(spec["input_per_1k"]),
                output_per_1k=float(spec["output_per_1k"]),
            )
        tool_costs: dict[str, float] = {
            k: float(v)
            for k, v in economic_section.get("tool_costs", {}).items()
        }
        return cls(model_pricing=models, tool_costs=tool_costs)

    # ------------------------------------------------------------------
    # Enforcement-time access
    # ------------------------------------------------------------------

    def get(self, model_name: str) -> ModelPricing | None:
        """Return pricing for ``model_name``, or None if not in registry."""
        return self._models.get(model_name)

    def tool_cost(self, tool_name: str) -> float:
        """Return fixed cost for a tool call, or 0.0 if not declared."""
        return self._tools.get(tool_name, 0.0)

    def cheapest_model(self) -> ModelPricing | None:
        """
        Return the model with the lowest blended cost (input + output per 1k).

        Used by EconomicPolicyEngine when building a REPLAN hint.
        Returns None if the registry is empty.
        """
        if not self._models:
            return None
        return min(
            self._models.values(),
            key=lambda p: p.input_per_1k + p.output_per_1k,
        )

    def models(self) -> tuple[ModelPricing, ...]:
        """Return all registered model pricings, sorted by blended cost ascending."""
        return tuple(
            sorted(
                self._models.values(),
                key=lambda p: p.input_per_1k + p.output_per_1k,
            )
        )
