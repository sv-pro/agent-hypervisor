"""
scenario_operator_service.py — Operator surface for scenarios (SYS-4A).

Thin wrapper over ScenarioRegistry and ScenarioTraceStore.
"""

from __future__ import annotations

from typing import Any, Optional

from .operator_event_log import OperatorEventLog
from .operator_models import ScenarioSummary
from .scenario_model import Scenario
from .scenario_registry import ScenarioRegistry
from .world_registry import WorldRegistry


class ScenarioOperatorService:
    """
    Operator-facing surface for scenario artifacts.

    Exposes last-run results and active-world alignment checks without
    re-running any execution.
    """

    def __init__(
        self,
        scenario_registry: ScenarioRegistry,
        trace_store: Optional[Any],  # ScenarioTraceStore | None
        event_log: OperatorEventLog,
    ) -> None:
        self._registry = scenario_registry
        self._trace_store = trace_store
        self._event_log = event_log

    # ------------------------------------------------------------------
    # List / inspect
    # ------------------------------------------------------------------

    def list_scenarios(self) -> list[ScenarioSummary]:
        scenarios = self._registry.list_scenarios()
        summaries: list[ScenarioSummary] = []
        for s in scenarios:
            last_run_at: Optional[str] = None
            last_diverged: Optional[bool] = None
            if self._trace_store is not None:
                recent = self._trace_store.list_recent(
                    limit=1, scenario_id=s.scenario_id
                )
                if recent:
                    entry = recent[0]
                    last_run_at = entry.get("ran_at") or entry.get("_stored_at")
                    last_diverged = not entry.get("divergence", {}).get("all_agree", True)

            summaries.append(
                ScenarioSummary(
                    scenario_id=s.scenario_id,
                    program_id=s.program_id,
                    worlds=tuple(
                        {"world_id": w.world_id, "version": w.version}
                        for w in s.worlds
                    ),
                    last_run_at=last_run_at,
                    last_diverged=last_diverged,
                )
            )

        self._event_log.log(
            action="list_scenarios",
            target_type="scenario",
            target_id="*",
            result="ok",
            details={"count": len(summaries)},
        )
        return summaries

    def get_scenario(self, scenario_id: str) -> Scenario:
        scenario = self._registry.get(scenario_id)
        self._event_log.log(
            action="get_scenario",
            target_type="scenario",
            target_id=scenario_id,
            result="ok",
        )
        return scenario

    def get_scenario_last_result(self, scenario_id: str) -> Optional[dict[str, Any]]:
        """Return the most recent ScenarioResult dict, or None if no history."""
        if self._trace_store is None:
            return None
        recent = self._trace_store.list_recent(limit=1, scenario_id=scenario_id)
        result = recent[0] if recent else None
        self._event_log.log(
            action="get_scenario_last_result",
            target_type="scenario",
            target_id=scenario_id,
            result="ok" if result else "none",
        )
        return result

    def compare_scenario_against_active_world(
        self,
        scenario_id: str,
        registry: WorldRegistry,
    ) -> dict[str, Any]:
        """
        Describe whether the scenario's referenced worlds include the active world
        and whether the last run diverged.

        Returns a plain dict suitable for CLI display or JSON serialisation.
        """
        scenario = self._registry.get(scenario_id)
        active = registry.get_active()

        scenario_world_keys = [
            {"world_id": w.world_id, "version": w.version} for w in scenario.worlds
        ]
        active_in_scenario = any(
            w.world_id == active.world_id for w in scenario.worlds
        ) if active else False

        last_result = self.get_scenario_last_result(scenario_id)
        last_diverged: Optional[bool] = None
        if last_result is not None:
            last_diverged = not last_result.get("divergence", {}).get("all_agree", True)

        return {
            "scenario_id": scenario_id,
            "active_world": (
                {"world_id": active.world_id, "version": active.version}
                if active else None
            ),
            "scenario_worlds": scenario_world_keys,
            "active_world_in_scenario": active_in_scenario,
            "last_diverged": last_diverged,
        }
