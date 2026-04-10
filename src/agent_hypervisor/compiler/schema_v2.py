"""schema_v2.py — Python dataclasses for World Manifest v2.0.

v2 extends the v1 action ontology with a structured world model:
  - Entity      — named objects in the agent's world
  - Actor       — execution participants with explicit trust tiers
  - DataClass   — classifications for data flowing through the system
  - TrustZone   — named regions with trust boundaries
  - SideEffectSurface — explicit per-action touch surfaces
  - TransitionPolicy  — allowed/forbidden zone-crossing rules
  - ConfirmationClass — named human-review requirements
  - ObservabilitySpec — per-action audit configuration

These types are construction-time artifacts. Once loaded and validated, they
are frozen inputs to the compiler. No mutable state after compilation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── World model types ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Entity:
    """A named object in the agent's world.

    Examples: user inbox, customer account, shared document, task queue.
    Entities are referenced by TrustZone and SideEffectSurface definitions.
    """

    name: str
    type: str  # user, account, document, queue, mailbox, contact, ...
    data_class: str  # references a DataClass by name
    identity_fields: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""


@dataclass(frozen=True)
class Actor:
    """An execution participant with an explicit trust tier.

    Actors include the primary agent, sub-agents, external services, and humans.
    Each actor has a trust tier and a bounded permission scope.
    """

    name: str
    type: str  # agent | sub_agent | service | human
    trust_tier: str  # TRUSTED | SEMI_TRUSTED | UNTRUSTED
    permission_scope: tuple[str, ...] = field(default_factory=tuple)  # capability names
    description: str = ""


@dataclass(frozen=True)
class DataClass:
    """A classification for data flowing through the system.

    Examples: public, internal, pii, credentials, financial.
    DataClass drives taint labels and confirmation requirements for data-flow policies.
    """

    name: str
    description: str
    taint_label: str  # label applied when this data class is tainted
    confirmation: str  # ConfirmationClass name required to handle this data
    retention: str = "session"  # how long audit records are retained: session, 90d, 365d, forever


@dataclass(frozen=True)
class TrustZone:
    """A named region of the world with a defined trust boundary.

    Trust zones partition the world into regions (e.g. internal_workspace,
    external_network). TransitionPolicies govern data flow between zones.
    """

    name: str
    description: str
    default_trust: str  # TRUSTED | SEMI_TRUSTED | UNTRUSTED
    entities: tuple[str, ...] = field(default_factory=tuple)  # entity names in this zone


@dataclass(frozen=True)
class SideEffectSurface:
    """Explicit declaration of what a single action can touch.

    Replaces the coarse side_effects list from v1. Each entry names the action
    and the entities or zones it can read from or write to.
    """

    action: str
    touches: tuple[str, ...] = field(default_factory=tuple)  # entity or zone names
    data_classes_affected: tuple[str, ...] = field(default_factory=tuple)  # DataClass names
    description: str = ""


@dataclass(frozen=True)
class TransitionPolicy:
    """An allowed or forbidden data transition between two trust zones.

    Transition policies define what data can cross zone boundaries and under
    what confirmation requirement. Denied transitions block the entire action.
    """

    from_zone: str
    to_zone: str
    allowed: bool
    confirmation: str = "auto"  # ConfirmationClass name
    description: str = ""


@dataclass(frozen=True)
class ConfirmationClass:
    """A named human-review requirement.

    Standard classes: auto, soft_confirm, hard_confirm, require_human.
    Custom classes may be defined for domain-specific workflows.
    """

    name: str
    description: str
    blocking: bool = False  # whether execution blocks waiting for human response


@dataclass(frozen=True)
class ObservabilityDefaults:
    """Default audit fields applied to all actions unless overridden."""

    log_fields: tuple[str, ...] = field(
        default_factory=lambda: ("action", "timestamp", "actor", "decision")
    )
    redact_fields: tuple[str, ...] = field(default_factory=tuple)
    retain_duration: str = "90d"


@dataclass(frozen=True)
class ObservabilitySpec:
    """Per-action audit configuration.

    Specifies what must be logged, redacted, and how long records are retained.
    Per-action specs override the defaults for that action only.
    """

    defaults: ObservabilityDefaults = field(default_factory=ObservabilityDefaults)
    per_action: dict[str, ObservabilityDefaults] = field(default_factory=dict)


# ── Root manifest type ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorldManifestV2:
    """Root type for a v2.0 World Manifest.

    A WorldManifestV2 is a frozen, compiled artifact. It cannot be modified
    after construction. All sections are validated at load time by loader_v2.

    Required sections: name, actions, trust_channels, capability_matrix.
    Optional sections: all world-model types (entities, actors, data_classes,
    trust_zones, confirmation_classes, side_effect_surfaces, transition_policies,
    observability).
    """

    # Manifest identity
    name: str
    version: str = "2.0"
    description: str = ""

    # World model (new in v2)
    entities: dict[str, Entity] = field(default_factory=dict)
    actors: dict[str, Actor] = field(default_factory=dict)
    data_classes: dict[str, DataClass] = field(default_factory=dict)
    trust_zones: dict[str, TrustZone] = field(default_factory=dict)
    confirmation_classes: dict[str, ConfirmationClass] = field(default_factory=dict)
    side_effect_surfaces: tuple[SideEffectSurface, ...] = field(default_factory=tuple)
    transition_policies: tuple[TransitionPolicy, ...] = field(default_factory=tuple)
    observability: ObservabilitySpec = field(default_factory=ObservabilitySpec)

    # Action ontology (required, extended from v1)
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    trust_channels: dict[str, dict[str, Any]] = field(default_factory=dict)
    capability_matrix: dict[str, list[str]] = field(default_factory=dict)

    # Optional sections carried from v1
    defaults: dict[str, str] = field(default_factory=dict)
    trust_levels: tuple[str, ...] = field(default_factory=tuple)
    taint_rules: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    escalation_rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    schemas: dict[str, Any] = field(default_factory=dict)
    predicates: dict[str, Any] = field(default_factory=dict)

    def action_names(self) -> list[str]:
        """Return the sorted list of declared action names."""
        return sorted(self.actions.keys())

    def entity_names(self) -> list[str]:
        """Return the sorted list of declared entity names."""
        return sorted(self.entities.keys())

    def data_class_names(self) -> list[str]:
        """Return the sorted list of declared data class names."""
        return sorted(self.data_classes.keys())

    def trust_zone_names(self) -> list[str]:
        """Return the sorted list of declared trust zone names."""
        return sorted(self.trust_zones.keys())

    def confirmation_class_names(self) -> list[str]:
        """Return the sorted list of declared confirmation class names."""
        return sorted(self.confirmation_classes.keys())


# ── Standard confirmation classes ─────────────────────────────────────────────

STANDARD_CONFIRMATION_CLASSES: dict[str, ConfirmationClass] = {
    "auto": ConfirmationClass(
        name="auto",
        description="No confirmation needed — execute immediately",
        blocking=False,
    ),
    "soft_confirm": ConfirmationClass(
        name="soft_confirm",
        description="Agent-level gate — dry-run, log, but do not block execution",
        blocking=False,
    ),
    "hard_confirm": ConfirmationClass(
        name="hard_confirm",
        description="Requires approval before execution (non-blocking wait)",
        blocking=True,
    ),
    "require_human": ConfirmationClass(
        name="require_human",
        description="Blocks execution until explicit human sign-off is received",
        blocking=True,
    ),
}

# ── Valid enumerations ────────────────────────────────────────────────────────

VALID_TRUST_TIERS = {"TRUSTED", "SEMI_TRUSTED", "UNTRUSTED"}
VALID_ACTOR_TYPES = {"agent", "sub_agent", "service", "human"}
VALID_ENTITY_TYPES = {"user", "account", "document", "queue", "mailbox", "contact", "other"}
