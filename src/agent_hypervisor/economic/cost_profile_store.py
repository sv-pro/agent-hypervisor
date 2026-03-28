"""
cost_profile_store.py — Trace-driven empirical cost profiles (Phase 3).

The CostProfileStore aggregates actual cost observations from execution traces
and produces percentile summaries (p50 / p90 / p99) per action and per
workflow.  These profiles are used at design-time to calibrate the static
estimates in PricingRegistry.

This module is Phase 3 infrastructure — it is deliberately minimal in Phase 1.
The interface is defined now so that trace recorders can start populating it;
the aggregation and percentile logic will be filled in during Phase 3.

Phase 1 contract:
  - ``record()`` is a no-op stub that accepts observations without error.
  - ``percentile()`` raises ``NotImplementedError``.
  - ``export()`` returns an empty dict.

This stub ensures that code written against this interface in Phase 1 will
work without modification in Phase 3, when real aggregation is added.

Design alignment:
  Profiles are compiled artifacts (produced offline from trace sets), not
  live runtime data.  The store is populated at design-time via
  ``ahc cost-profile <trace-set>`` and compiled into the manifest before
  the next deployment.  The enforcement path never reads live profile data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostObservation:
    """
    One actual-cost observation from a completed execution trace.

    Attributes:
        action_name:   The action that was executed.
        workflow_id:   Optional workflow identifier for per-workflow profiling.
        model_name:    The model used, if applicable.
        actual_cost:   The real USD cost reported by the provider after execution.
        input_tokens:  Actual input token count (from provider response).
        output_tokens: Actual output token count (from provider response).
    """
    action_name:   str
    actual_cost:   float
    workflow_id:   str = ""
    model_name:    str = ""
    input_tokens:  int = 0
    output_tokens: int = 0


@dataclass
class CostProfile:
    """
    Percentile cost profile for one (action, model) pair.

    Populated in Phase 3 from aggregated observations.
    All costs are in USD.
    """
    action_name: str
    model_name:  str
    p50:         float = 0.0
    p90:         float = 0.0
    p99:         float = 0.0
    sample_count: int = 0


class CostProfileStore:
    """
    Aggregates actual cost observations and produces percentile profiles.

    Phase 1: stub implementation — records observations but does not aggregate.
    Phase 3: real percentile computation over stored observations.

    The store is populated offline (design-time) from execution trace sets.
    It is never read on the live enforcement path.
    """

    def __init__(self) -> None:
        # Phase 1: flat list of raw observations.
        # Phase 3: replace with a proper time-series store.
        self._observations: list[CostObservation] = []

    def record(self, observation: CostObservation) -> None:
        """
        Record one actual-cost observation.

        Phase 1: stores the observation in memory without aggregation.
        Phase 3: will flush to a persistent store for offline profiling.
        """
        self._observations.append(observation)

    def percentile(
        self,
        action_name: str,
        model_name: str,
        p: float,
    ) -> float:
        """
        Return the p-th percentile cost for (action_name, model_name).

        Phase 1: raises NotImplementedError — not yet implemented.
        Phase 3: returns the computed percentile from aggregated observations.

        Args:
            action_name: The action to query.
            model_name:  The model to query.
            p:           Percentile in [0, 100] (e.g. 90 for p90).
        """
        raise NotImplementedError(
            "CostProfileStore.percentile() is a Phase 3 feature. "
            "Collect observations via record() and aggregate offline."
        )

    def export(self) -> dict[str, Any]:
        """
        Export all observations as a plain dict (for offline processing).

        Phase 1: returns a list of raw observations.
        Phase 3: returns aggregated profiles keyed by (action, model).
        """
        return {
            "observations": [
                {
                    "action_name":   obs.action_name,
                    "workflow_id":   obs.workflow_id,
                    "model_name":    obs.model_name,
                    "actual_cost":   obs.actual_cost,
                    "input_tokens":  obs.input_tokens,
                    "output_tokens": obs.output_tokens,
                }
                for obs in self._observations
            ]
        }

    def observation_count(self) -> int:
        """Return the number of recorded observations."""
        return len(self._observations)
