"""
models.py — Data models for the SYS-4A Operator Surface.

These models expose programs, scenarios, and worlds as managed runtime
artifacts. They are pure data classes meant for serialisation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agent_hypervisor.program_layer import WorldRef


# ---------------------------------------------------------------------------
# Logging Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OperatorEvent:
    """An event representing an operator action."""
    timestamp: str  # ISO-8601
    action: str
    target_object: str
    result: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "target_object": self.target_object,
            "result": self.result,
        }

    @classmethod
    def create(cls, action: str, target_object: str, result: Any) -> OperatorEvent:
        return cls(
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            action=action,
            target_object=target_object,
            result=result,
        )


@dataclass(frozen=True)
class WorldActivationRecord:
    """Explicit record of a world activation (or rollback)."""
    activation_id: str
    world_id: str
    version: str
    activated_at: str  # ISO-8601
    previous_world_id: Optional[str] = field(default=None)
    previous_version: Optional[str] = field(default=None)
    activated_by: Optional[str] = field(default=None)
    reason: Optional[str] = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "world_id": self.world_id,
            "version": self.version,
            "previous_world_id": self.previous_world_id,
            "previous_version": self.previous_version,
            "activated_at": self.activated_at,
            "activated_by": self.activated_by,
            "reason": self.reason,
        }

    @classmethod
    def create(
        cls,
        world_id: str,
        version: str,
        previous_world_id: Optional[str] = None,
        previous_version: Optional[str] = None,
        activated_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> WorldActivationRecord:
        return cls(
            activation_id=f"act-{uuid.uuid4().hex[:12]}",
            world_id=world_id,
            version=version,
            previous_world_id=previous_world_id,
            previous_version=previous_version,
            activated_at=datetime.now(tz=timezone.utc).isoformat(),
            activated_by=activated_by,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# Summary Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProgramSummary:
    """Summarized view of a program context for an operator."""
    program_id: str
    status: str
    world_version_at_creation: str
    compatible_with_active_world: bool
    compatibility_checked_against: Optional[dict[str, str]]
    last_replay_verdict: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "status": self.status,
            "world_version_at_creation": self.world_version_at_creation,
            "compatible_with_active_world": self.compatible_with_active_world,
            "compatibility_checked_against": self.compatibility_checked_against,
            "last_replay_verdict": self.last_replay_verdict,
        }


@dataclass(frozen=True)
class ScenarioSummary:
    """Summarized view of a scenario context for an operator."""
    scenario_id: str
    program_id: Optional[str]
    worlds: list[dict[str, str]]  # list of WorldRef dicts
    last_run_at: Optional[str]
    last_diverged: Optional[bool]
    last_evaluated_worlds: Optional[list[str]]  # The worlds compared last

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "program_id": self.program_id,
            "worlds": self.worlds,
            "last_run_at": self.last_run_at,
            "last_diverged": self.last_diverged,
            "last_evaluated_worlds": self.last_evaluated_worlds,
        }


# ---------------------------------------------------------------------------
# Impact Preview
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActivationImpactReport:
    """Result of previewing the impact of changing the active world."""
    target_world: dict[str, str]
    current_world: Optional[dict[str, str]]
    affected_programs: list[dict[str, Any]]
    affected_scenarios: list[dict[str, Any]]
    totals: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_world": self.target_world,
            "current_world": self.current_world,
            "affected_programs": self.affected_programs,
            "affected_scenarios": self.affected_scenarios,
            "totals": self.totals,
        }
