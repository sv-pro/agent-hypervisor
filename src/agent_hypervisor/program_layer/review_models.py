"""
review_models.py — Program review and minimization data models (PL-3).

Defines the artifact produced by the Program Review & Minimization phase:

    CandidateStep    — a single step from a raw candidate program (from PL-2 traces)
    RemovedStep      — records a step removed during minimization
    ParamChange      — records a parameter reduction during minimization
    CapabilityChange — records a capability surface reduction during minimization
    ProgramDiff      — complete diff between original and minimized programs
    ProgramMetadata  — provenance and lifecycle metadata
    ProgramStatus    — lifecycle states (proposed → reviewed → accepted | rejected)
    ReviewedProgram  — the complete reviewed artifact (frozen, immutable)

All models are frozen dataclasses.  Transition between states produces new
instances via dataclasses.replace() — the original is never mutated.

Serialization:
    All models implement to_dict() → dict and from_dict(data) → instance.
    The dict format is JSON-safe and stable across PL-3.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class ProgramStatus(str, Enum):
    """
    Lifecycle states for a ReviewedProgram.

    Allowed transitions (enforced by review_lifecycle.py):
        proposed → reviewed
        reviewed → accepted
        reviewed → rejected
    """

    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# CandidateStep
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateStep:
    """
    A single step from a raw candidate program.

    Derived from a PL-2 execution trace.  Carries optional provenance and
    capability annotations not present in the basic Step model.

    Fields:
        tool              — action/tool name (matches world manifest action space)
        params            — key-value parameters (must be JSON-safe)
        provenance        — optional trace identifier (where this step came from)
        capabilities_used — optional tuple of capability patterns observed
                            (e.g. "http_request:any", "file_read:local")
    """

    tool: str
    params: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    provenance: Optional[str] = field(default=None, hash=False, compare=False)
    capabilities_used: Optional[tuple[str, ...]] = field(
        default=None, hash=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.tool, str) or not self.tool.strip():
            raise ValueError(
                f"CandidateStep.tool must be a non-empty string, got {self.tool!r}"
            )
        if not isinstance(self.params, dict):
            raise TypeError(
                f"CandidateStep.params must be a dict, "
                f"got {type(self.params).__name__!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "params": self.params,
            "provenance": self.provenance,
            "capabilities_used": (
                list(self.capabilities_used)
                if self.capabilities_used is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateStep":
        caps = data.get("capabilities_used")
        return cls(
            tool=data["tool"],
            params=data.get("params", {}),
            provenance=data.get("provenance"),
            capabilities_used=tuple(caps) if caps is not None else None,
        )


# ---------------------------------------------------------------------------
# Diff components
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RemovedStep:
    """Records a step that was removed during minimization."""

    index: int   # original index (0-based)
    tool: str    # action name of the removed step
    reason: str  # human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "tool": self.tool, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RemovedStep":
        return cls(index=data["index"], tool=data["tool"], reason=data["reason"])


@dataclass(frozen=True)
class ParamChange:
    """Records a parameter reduction applied to a step during minimization."""

    step_index: int  # 0-based index in the original step list
    field: str       # parameter key that was changed
    before: Any      # original value (any JSON-safe type)
    after: Any       # reduced value (None means key was dropped)
    reason: str      # human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "field": self.field,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParamChange":
        return cls(
            step_index=data["step_index"],
            field=data["field"],
            before=data["before"],
            after=data["after"],
            reason=data["reason"],
        )


@dataclass(frozen=True)
class CapabilityChange:
    """Records a capability surface reduction applied during minimization."""

    step_index: int  # 0-based index in the original step list
    before: str      # broader capability pattern (e.g. "http_request:any")
    after: str       # narrower capability pattern (e.g. "http_request:api.example.com/*")
    reason: str      # human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapabilityChange":
        return cls(
            step_index=data["step_index"],
            before=data["before"],
            after=data["after"],
            reason=data["reason"],
        )


@dataclass(frozen=True)
class ProgramDiff:
    """
    Complete diff between original and minimized programs.

    Records every transformation applied during minimization:
        removed_steps        — steps eliminated entirely
        param_changes        — parameter values reduced or dropped
        capability_reduction — capability patterns narrowed

    An empty diff (all tuples empty) means no minimization was possible —
    the minimized program is identical to the original.
    """

    removed_steps: tuple[RemovedStep, ...] = field(default_factory=tuple)
    param_changes: tuple[ParamChange, ...] = field(default_factory=tuple)
    capability_reduction: tuple[CapabilityChange, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        """True if no transformations were applied."""
        return (
            len(self.removed_steps) == 0
            and len(self.param_changes) == 0
            and len(self.capability_reduction) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "removed_steps": [s.to_dict() for s in self.removed_steps],
            "param_changes": [c.to_dict() for c in self.param_changes],
            "capability_reduction": [c.to_dict() for c in self.capability_reduction],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgramDiff":
        return cls(
            removed_steps=tuple(
                RemovedStep.from_dict(s) for s in data.get("removed_steps", [])
            ),
            param_changes=tuple(
                ParamChange.from_dict(c) for c in data.get("param_changes", [])
            ),
            capability_reduction=tuple(
                CapabilityChange.from_dict(c)
                for c in data.get("capability_reduction", [])
            ),
        )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProgramMetadata:
    """
    Provenance and lifecycle metadata for a ReviewedProgram.

    Fields:
        created_from_trace — trace_id from which this program was extracted
        world_version      — the world manifest version at creation time
        created_at         — ISO-8601 timestamp of program creation
        reviewer_notes     — optional human notes added during review
    """

    created_from_trace: Optional[str]
    world_version: str
    created_at: str          # ISO-8601
    reviewer_notes: Optional[str] = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_from_trace": self.created_from_trace,
            "world_version": self.world_version,
            "created_at": self.created_at,
            "reviewer_notes": self.reviewer_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgramMetadata":
        return cls(
            created_from_trace=data.get("created_from_trace"),
            world_version=data.get("world_version", "unknown"),
            created_at=data.get(
                "created_at", datetime.now(tz=timezone.utc).isoformat()
            ),
            reviewer_notes=data.get("reviewer_notes"),
        )


# ---------------------------------------------------------------------------
# ReviewedProgram
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewedProgram:
    """
    A candidate program after review and minimization.

    Immutable once constructed.  Status transitions produce new instances
    via dataclasses.replace() — the original is never mutated.

    Fields:
        id               — stable unique identifier (e.g. "prog-abc123ef4567")
        status           — current lifecycle state (ProgramStatus)
        original_steps   — the unmodified steps from the candidate program
        minimized_steps  — steps after minimization (subset + reduced params)
        diff             — explicit record of every transformation applied
        metadata         — provenance and lifecycle metadata

    Invariants enforced at construction:
        - id must be a non-empty string
        - original_steps must be a non-empty tuple of CandidateStep
        - minimized_steps must be a tuple of CandidateStep
        - len(minimized_steps) <= len(original_steps)  [minimization never adds]
        - diff must be a ProgramDiff
        - metadata must be a ProgramMetadata

    Serialization:
        to_dict()       → JSON-safe dict (stable schema across PL-3)
        from_dict(data) → ReviewedProgram instance
    """

    id: str
    status: ProgramStatus
    original_steps: tuple[CandidateStep, ...]
    minimized_steps: tuple[CandidateStep, ...]
    diff: ProgramDiff
    metadata: ProgramMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError(
                f"ReviewedProgram.id must be a non-empty string, got {self.id!r}"
            )
        if not isinstance(self.original_steps, tuple):
            raise TypeError(
                "ReviewedProgram.original_steps must be a tuple, "
                f"got {type(self.original_steps).__name__!r}"
            )
        if len(self.original_steps) == 0:
            raise ValueError("ReviewedProgram.original_steps must not be empty")
        for i, step in enumerate(self.original_steps):
            if not isinstance(step, CandidateStep):
                raise TypeError(
                    f"ReviewedProgram.original_steps[{i}] must be a CandidateStep, "
                    f"got {type(step).__name__!r}"
                )
        if not isinstance(self.minimized_steps, tuple):
            raise TypeError(
                "ReviewedProgram.minimized_steps must be a tuple, "
                f"got {type(self.minimized_steps).__name__!r}"
            )
        for i, step in enumerate(self.minimized_steps):
            if not isinstance(step, CandidateStep):
                raise TypeError(
                    f"ReviewedProgram.minimized_steps[{i}] must be a CandidateStep, "
                    f"got {type(step).__name__!r}"
                )
        if len(self.minimized_steps) > len(self.original_steps):
            raise ValueError(
                "ReviewedProgram.minimized_steps cannot have more steps than "
                f"original_steps ({len(self.minimized_steps)} > "
                f"{len(self.original_steps)})"
            )
        if not isinstance(self.diff, ProgramDiff):
            raise TypeError(
                f"ReviewedProgram.diff must be a ProgramDiff, "
                f"got {type(self.diff).__name__!r}"
            )
        if not isinstance(self.metadata, ProgramMetadata):
            raise TypeError(
                f"ReviewedProgram.metadata must be a ProgramMetadata, "
                f"got {type(self.metadata).__name__!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict.  Schema is stable across PL-3."""
        return {
            "id": self.id,
            "status": self.status.value,
            "original_steps": [s.to_dict() for s in self.original_steps],
            "minimized_steps": [s.to_dict() for s in self.minimized_steps],
            "diff": self.diff.to_dict(),
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewedProgram":
        """Deserialize from a dict produced by to_dict()."""
        return cls(
            id=data["id"],
            status=ProgramStatus(data["status"]),
            original_steps=tuple(
                CandidateStep.from_dict(s) for s in data["original_steps"]
            ),
            minimized_steps=tuple(
                CandidateStep.from_dict(s) for s in data["minimized_steps"]
            ),
            diff=ProgramDiff.from_dict(data["diff"]),
            metadata=ProgramMetadata.from_dict(data["metadata"]),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_program_id() -> str:
    """Generate a stable, unique program identifier."""
    return f"prog-{uuid.uuid4().hex[:12]}"
