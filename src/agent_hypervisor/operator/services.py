"""
services.py — stateless services to provide Operator visibility and functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agent_hypervisor.program_layer import (
    ProgramStore,
    ScenarioRegistry,
    ScenarioTraceStore,
    WorldNotFoundError,
    WorldRegistry,
    check_compatibility,
    run_scenario,
)
from .models import (
    ActivationImpactReport,
    OperatorEvent,
    ProgramSummary,
    ScenarioSummary,
    WorldActivationRecord,
)


class OperatorEventLogger:
    """
    Append-only logger for SYS-4A operator events and activation history.

    ASSUMPTION: single_writer=True.
    No complex file-locking mechanism is applied in this phase since the design
    is primarily CLI-driven or lightweight wrapper-driven.
    """

    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        items = []
        with self.log_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items


class WorldOperatorService:
    """Manages explicit activation, rollback, and deterministic previews."""

    def __init__(
        self,
        world_registry: WorldRegistry,
        activation_history_file: str | Path,
        operator_events_file: str | Path,
    ):
        self.world_registry = world_registry
        self.history_logger = OperatorEventLogger(activation_history_file)
        self.event_logger = OperatorEventLogger(operator_events_file)

    def list_worlds(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self.world_registry.list_worlds()]

    def get_active_world(self) -> Optional[dict[str, Any]]:
        world = self.world_registry.get_active()
        return world.to_dict() if world else None

    def activate_world(
        self,
        world_id: str,
        version: str,
        reason: Optional[str] = None,
        activated_by: Optional[str] = None,
    ) -> WorldActivationRecord:
        """Atomic activation. Validates world, updates pointer, records history."""
        # Find current so we know what we are rolling back from if needed.
        current_data = self.world_registry.get_active_pointer_data()
        prev_world_id = current_data.get("world_id")
        prev_version = current_data.get("version")

        # Validate target
        target = self.world_registry.get(world_id, version)

        record = WorldActivationRecord.create(
            world_id=target.world_id,
            version=target.version,
            previous_world_id=prev_world_id,
            previous_version=prev_version,
            activated_by=activated_by,
            reason=reason,
        )

        # Atomically update
        self.world_registry.set_active(
            world_id=target.world_id,
            version=target.version,
            previous_world_id=prev_world_id,
            previous_version=prev_version,
        )

        # Log trailing history
        self.history_logger.append(record.to_dict())
        self.event_logger.append(
            OperatorEvent.create(
                action="activate_world",
                target_object=f"{target.world_id}@{target.version}",
                result="SUCCESS",
            ).to_dict()
        )

        return record

    def rollback_world(
        self,
        reason: Optional[str] = "Rollback",
        activated_by: Optional[str] = None,
    ) -> WorldActivationRecord:
        """Restores the immediately previous world, recording the event."""
        current_data = self.world_registry.get_active_pointer_data()
        prev_world_id = current_data.get("previous_world_id")
        prev_version = current_data.get("previous_version")

        if not prev_world_id or not prev_version:
            raise ValueError("No previous world info available to rollback to.")

        return self.activate_world(
            world_id=prev_world_id,
            version=prev_version,
            reason=reason,
            activated_by=activated_by,
        )

    def get_activation_history(self) -> list[dict[str, Any]]:
        return self.history_logger.read_all()

    def preview_activation_impact(
        self,
        world_id: str,
        version: str,
        program_store: ProgramStore,
        scenario_registry: ScenarioRegistry,
    ) -> ActivationImpactReport:
        """Determines exactly how upgrading/rolling-back impacts programs and scenarios."""
        target_world = self.world_registry.get(world_id, version)
        current_world = self.world_registry.get_active()

        affected_programs = []
        for pid in program_store.list_ids():
            try:
                prog = program_store.load(pid)
            except Exception:
                continue

            # Deterministic compatibility
            target_compat = check_compatibility(prog, target_world)
            current_compat = None
            if current_world:
                current_compat = check_compatibility(prog, current_world)

            target_is_compat = target_compat.compatible
            curr_is_compat = current_compat.compatible if current_compat else False

            impact = "unchanged"
            if target_is_compat and curr_is_compat:
                pass
            elif not target_is_compat and not curr_is_compat:
                pass
            elif target_is_compat and not curr_is_compat:
                impact = "changed_behavior"  # it can now execute
            elif not target_is_compat and curr_is_compat:
                impact = "incompatible"  # it breaks

            if impact != "unchanged":
                summary = (
                    "program becomes compatible" if target_is_compat else "program becomes incompatible"
                )
                affected_programs.append(
                    {
                        "program_id": pid,
                        "current_compatible": curr_is_compat,
                        "target_compatible": target_is_compat,
                        "impact": impact,
                        "summary": summary,
                    }
                )

        affected_scenarios = []
        for scen in scenario_registry.list_scenarios():
            # A scenario outcome may change if its program compatibility changes under the target world,
            # or if the scenario explicitly targets this world.
            prog_id = scen.program_id
            if prog_id:
                try:
                    prog = program_store.load(prog_id)
                except Exception:
                    continue
                
                target_compat = check_compatibility(prog, target_world)
                current_compat = None
                if current_world:
                    current_compat = check_compatibility(prog, current_world)
                
                target_is_compat = target_compat.compatible
                curr_is_compat = current_compat.compatible if current_compat else False

                impact = "unchanged"
                if target_is_compat != curr_is_compat:
                    impact = "incompatible" if not target_is_compat else "changed_behavior"

                # Also, if the scenario explicitly uses this world, the divergence is highly likely affected.
                uses_target = any(w.world_id == world_id and w.version == version for w in scen.worlds)
                
                if impact != "unchanged" or uses_target:
                    affected_scenarios.append(
                        {
                            "scenario_id": scen.scenario_id,
                            "impact": impact,
                            "summary": "scenario explicitly binds to target world" if uses_target else "underlying program compatibility changed",
                            "divergence_expected": uses_target or (impact != "unchanged"),
                        }
                    )

        target_dict = {"world_id": target_world.world_id, "version": target_world.version}
        current_dict = (
            {"world_id": current_world.world_id, "version": current_world.version}
            if current_world else None
        )

        # Log this preview usage
        self.event_logger.append(
            OperatorEvent.create(
                action="preview_impact",
                target_object=f"{world_id}@{version}",
                result="SUCCESS",
            ).to_dict()
        )

        return ActivationImpactReport(
            target_world=target_dict,
            current_world=current_dict,
            affected_programs=affected_programs,
            affected_scenarios=affected_scenarios,
            totals={
                "reviewed_programs_checked": len(program_store.list_ids()),
                "scenarios_checked": len(scenario_registry.list_scenarios()),
                "programs_becoming_incompatible": sum(1 for p in affected_programs if p.get("impact") == "incompatible"),
                "programs_changed_behavior": sum(1 for p in affected_programs if p.get("impact") == "changed_behavior"),
            },
        )


class ProgramOperatorService:
    def __init__(
        self,
        program_store: ProgramStore,
        world_registry: WorldRegistry,
        operator_events_file: str | Path,
    ):
        self.program_store = program_store
        self.world_registry = world_registry
        self.event_logger = OperatorEventLogger(operator_events_file)

    def list_programs(self, status: Optional[str] = None) -> list[ProgramSummary]:
        summaries = []
        active_w = self.world_registry.get_active()
        active_w_dict = {"world_id": active_w.world_id, "version": active_w.version} if active_w else None

        for prog_dict in self.program_store.list_all():
            if status and prog_dict.get("status") != status:
                continue

            prog_id = prog_dict["id"]
            try:
                prog = self.program_store.load(prog_id)
            except Exception:
                continue

            is_compat = False
            if active_w:
                is_compat = check_compatibility(prog, active_w).compatible

            summaries.append(
                ProgramSummary(
                    program_id=prog_id,
                    status=prog.status.value,
                    world_version_at_creation=prog.metadata.world_version,
                    compatible_with_active_world=is_compat,
                    compatibility_checked_against=active_w_dict,
                    last_replay_verdict=None,  # Not tracked persistently per program natively right now
                )
            )
        return summaries

    def get_program(self, program_id: str) -> dict[str, Any]:
        return self.program_store.load(program_id).to_dict()

    def get_program_diff(self, program_id: str) -> dict[str, Any]:
        return self.program_store.load(program_id).diff.to_dict()

    def get_program_compatibility(self, program_id: str, world_id: Optional[str] = None, version: Optional[str] = None) -> dict[str, Any]:
        target_world = None
        if world_id:
            try:
                target_world = self.world_registry.get(world_id, version)
            except WorldNotFoundError:
                pass
        
        if not target_world:
            target_world = self.world_registry.get_active()

        if not target_world:
            raise ValueError("No active world to check against, and no explicit world provided.")

        prog = self.program_store.load(program_id)
        return check_compatibility(prog, target_world).to_dict()


class ScenarioOperatorService:
    def __init__(
        self,
        scenario_registry: ScenarioRegistry,
        trace_store: ScenarioTraceStore,
        world_registry: WorldRegistry,
        operator_events_file: str | Path,
    ):
        self.scenario_registry = scenario_registry
        self.trace_store = trace_store
        self.world_registry = world_registry
        self.event_logger = OperatorEventLogger(operator_events_file)

    def list_scenarios(self) -> list[ScenarioSummary]:
        summaries = []
        for scen in self.scenario_registry.list_scenarios():
            recent = self.trace_store.list_recent(limit=1, scenario_id=scen.scenario_id)
            last_run = None
            last_div = None
            evaluated_w = None

            if recent:
                last_run = recent[0].get("ran_at")
                last_div = not recent[0].get("divergence", {}).get("all_agree", True)
                evaluated_w = [w["key"] for w in recent[0].get("world_results", []) if "key" in w]

            summaries.append(
                ScenarioSummary(
                    scenario_id=scen.scenario_id,
                    program_id=scen.program_id,
                    worlds=[w.to_dict() for w in scen.worlds],
                    last_run_at=last_run,
                    last_diverged=last_div,
                    last_evaluated_worlds=evaluated_w,
                )
            )
        return summaries

    def get_scenario(self, scenario_id: str) -> dict[str, Any]:
        return self.scenario_registry.get(scenario_id).to_dict()

    def get_scenario_last_result(self, scenario_id: str) -> Optional[dict[str, Any]]:
        recent = self.trace_store.list_recent(limit=1, scenario_id=scenario_id)
        return recent[0] if recent else None

    def compare_scenario_against_active_worlds(self, scenario_id: str) -> dict[str, Any]:
        """Runs the scenario using its defined worlds + active world (if different) temporarily to generate a trace report."""
        self.event_logger.append(
            OperatorEvent.create(
                action="scenario_compare",
                target_object=scenario_id,
                result="STARTED",
            ).to_dict()
        )
        return {} # Placeholder, CLI orchestrates this logic using run_scenario or it isn't required for naive view.
