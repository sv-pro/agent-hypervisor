"""
world_operator_service.py — Lifecycle management for Worlds (SYS-4A).

Sits above WorldRegistry; does not touch the sealed runtime kernel.

Responsibilities:
  - activate_world with history recording
  - rollback_world (restores previous)
  - get_activation_history (append-only JSONL)
  - preview_activation_impact (deterministic, no execution)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .compatibility import check_compatibility
from .operator_event_log import OperatorEventLog
from .operator_models import (
    ActivationImpactReport,
    ProgramImpact,
    ScenarioImpact,
    WorldActivationRecord,
)
from .world_registry import WorldDescriptor, WorldNotFoundError, WorldRegistry

if TYPE_CHECKING:
    from .program_store import ProgramStore
    from .review_models import ProgramStatus
    from .scenario_registry import ScenarioRegistry
    from .scenario_trace_store import ScenarioTraceStore


class RollbackError(RuntimeError):
    """Raised when rollback cannot be performed (e.g. no previous world)."""


class WorldOperatorService:
    """
    Lifecycle management shell for Worlds.

    All state mutation goes through this service so that every activation
    and rollback is recorded in the append-only history file.

    Args:
        registry:       WorldRegistry over the worlds directory.
        history_file:   Path to the JSONL activation history file.
                        Created on first write; parent dirs created automatically.
        event_log:      OperatorEventLog for cross-surface event recording.
    """

    def __init__(
        self,
        registry: WorldRegistry,
        history_file: str | Path,
        event_log: OperatorEventLog,
    ) -> None:
        self._registry = registry
        self._history_file = Path(history_file)
        self._event_log = event_log

    # ------------------------------------------------------------------
    # Read-only queries
    # ------------------------------------------------------------------

    def list_worlds(self) -> list[WorldDescriptor]:
        return self._registry.list_worlds()

    def get_active_world(self) -> Optional[WorldDescriptor]:
        return self._registry.get_active()

    def get_activation_history(self) -> list[WorldActivationRecord]:
        """Return activation history oldest-first."""
        if not self._history_file.exists():
            return []
        records: list[WorldActivationRecord] = []
        try:
            for line in self._history_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(WorldActivationRecord.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError:
            return []
        return records

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def activate_world(
        self,
        world_id: str,
        version: Optional[str] = None,
        *,
        reason: Optional[str] = None,
        activated_by: Optional[str] = None,
        _is_rollback: bool = False,
    ) -> WorldActivationRecord:
        """
        Activate a world, recording the transition in history.

        Validates the target world before changing the active pointer.
        If loading the target fails, the active pointer is unchanged.

        Returns the new WorldActivationRecord.
        """
        # Snapshot previous state before mutating.
        previous = self._registry.get_active()
        previous_world_id = previous.world_id if previous else None
        previous_version = previous.version if previous else None

        # Resolve version and validate — WorldRegistry.set_active() does the
        # atomic write and raises WorldNotFoundError on failure.
        resolved = self._registry.get(world_id, version)
        self._registry.set_active(resolved.world_id, resolved.version)

        record = WorldActivationRecord(
            activation_id=uuid.uuid4().hex[:16],
            world_id=resolved.world_id,
            version=resolved.version,
            previous_world_id=previous_world_id,
            previous_version=previous_version,
            activated_at=datetime.now(tz=timezone.utc).isoformat(),
            activated_by=activated_by,
            reason=reason,
            is_rollback=_is_rollback,
        )

        self._append_history(record)
        self._event_log.log(
            action="rollback_world" if _is_rollback else "activate_world",
            target_type="world",
            target_id=resolved.world_id,
            result="ok",
            details={
                "version": resolved.version,
                "previous_world_id": previous_world_id,
                "previous_version": previous_version,
                "reason": reason,
            },
        )
        return record

    def rollback_world(self, *, reason: Optional[str] = None) -> WorldActivationRecord:
        """
        Restore the world that was active immediately before the current one.

        Reads the most recent history record to find the previous world.
        Raises RollbackError if there is no previous world to restore.
        """
        history = self.get_activation_history()
        if not history:
            raise RollbackError(
                "No activation history found. Cannot roll back."
            )

        latest = history[-1]
        if not latest.previous_world_id or not latest.previous_version:
            raise RollbackError(
                f"The most recent activation ({latest.world_id} {latest.version}) "
                "has no previous world recorded. Cannot roll back."
            )

        rollback_reason = reason or "rollback"
        return self.activate_world(
            latest.previous_world_id,
            latest.previous_version,
            reason=rollback_reason,
            _is_rollback=True,
        )

    # ------------------------------------------------------------------
    # Impact preview
    # ------------------------------------------------------------------

    def preview_activation_impact(
        self,
        world_id: str,
        version: Optional[str],
        store: "ProgramStore",
        scenario_registry: "ScenarioRegistry",
        scenario_trace_store: Optional["ScenarioTraceStore"] = None,
    ) -> ActivationImpactReport:
        """
        Deterministic impact report for a proposed world activation.

        Checks all reviewed/accepted programs against the target world and
        flags scenarios that reference it.  No execution occurs.
        """
        from .review_models import ProgramStatus

        target_world = self._registry.get(world_id, version)
        current_world = self._registry.get_active()

        program_impacts: list[ProgramImpact] = []
        for prog_id in store.list_ids():
            try:
                prog = store.load(prog_id)
            except (KeyError, ValueError):
                continue
            if prog.status not in (ProgramStatus.REVIEWED, ProgramStatus.ACCEPTED):
                continue

            current_compat: Optional[bool] = None
            if current_world is not None:
                current_compat = check_compatibility(prog, current_world).compatible

            target_compat = check_compatibility(prog, target_world).compatible

            if current_compat is None:
                summary = (
                    f"target={'compatible' if target_compat else 'incompatible'}"
                    " (no current world)"
                )
            elif current_compat == target_compat:
                status_word = "compatible" if target_compat else "incompatible"
                summary = f"unchanged — {status_word} in both"
            elif not current_compat and target_compat:
                summary = "gains compatibility under target world"
            else:
                summary = "loses compatibility under target world"

            program_impacts.append(
                ProgramImpact(
                    program_id=prog.id,
                    current_compatible=current_compat,
                    target_compatible=target_compat,
                    summary=summary,
                )
            )

        scenario_impacts: list[ScenarioImpact] = []
        for scenario in scenario_registry.list_scenarios():
            scenario_world_ids = {w.world_id for w in scenario.worlds}
            involves_target = target_world.world_id in scenario_world_ids

            last_diverged: Optional[bool] = None
            if scenario_trace_store is not None:
                recent = scenario_trace_store.list_recent(
                    limit=1, scenario_id=scenario.scenario_id
                )
                if recent:
                    last_diverged = not recent[0].get("divergence", {}).get(
                        "all_agree", True
                    )

            divergence_expected = bool(
                involves_target or (last_diverged is True)
            )

            if involves_target:
                summary = (
                    f"scenario references target world {target_world.world_id}; "
                    "outcomes may change"
                )
            elif last_diverged:
                summary = "previously diverged; may be affected by world change"
            else:
                summary = "no direct reference to target world"

            scenario_impacts.append(
                ScenarioImpact(
                    scenario_id=scenario.scenario_id,
                    summary=summary,
                    divergence_expected=divergence_expected,
                )
            )

        becoming_incompatible = sum(
            1 for p in program_impacts
            if p.current_compatible is True and not p.target_compatible
        )

        totals = {
            "reviewed_programs_checked": len(program_impacts),
            "scenarios_checked": len(scenario_impacts),
            "programs_becoming_incompatible": becoming_incompatible,
        }

        self._event_log.log(
            action="preview_activation_impact",
            target_type="world",
            target_id=target_world.world_id,
            result="ok",
            details={
                "version": target_world.version,
                "totals": totals,
            },
        )

        return ActivationImpactReport(
            target_world={"world_id": target_world.world_id, "version": target_world.version},
            current_world=(
                {"world_id": current_world.world_id, "version": current_world.version}
                if current_world else None
            ),
            affected_programs=tuple(program_impacts),
            affected_scenarios=tuple(scenario_impacts),
            totals=totals,
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append_history(self, record: WorldActivationRecord) -> None:
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
        with self._history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
