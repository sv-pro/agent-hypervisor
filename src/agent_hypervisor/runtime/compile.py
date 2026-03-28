"""
Compile Phase
=============

Transforms world_manifest.yaml into an immutable CompiledPolicy.

This runs ONCE at startup via build_runtime(). After compilation:
  - world_manifest.yaml is not accessed by any runtime component
  - All policy decisions live in frozen Python data structures
  - No string comparisons, no YAML parsing, no dict iteration at request time

Compile outputs:
  actions:           MappingProxyType[str, CompiledAction]
                     Sealed — CallerCode cannot add or modify entries.
  capability_matrix: frozenset[tuple[TrustLevel, ActionType]]
                     O(1) membership test — no loops, no strings.
  taint_rules:       tuple[TaintRule, ...]
                     Immutable ordered sequence.
  trust_map:         MappingProxyType[str, TrustLevel]
                     Channel identity → TrustLevel, resolved at IR build time.

Sealing mechanism for CompiledAction:
  _COMPILE_GATE is a module-private object() sentinel. CompiledAction.__init__
  checks that the caller passed _COMPILE_GATE as the _gate argument. External
  code cannot import _COMPILE_GATE (it is module-private by naming convention
  and is not exported). This makes CompiledAction construction outside the
  compile phase a TypeError at runtime, catching accidental bypass immediately.

Execution boundary:
  CompiledAction is PURE METADATA. It carries name, action_type, and
  approval_required — nothing more. There is NO handler, NO _invoke() method,
  and NO callable behavior on objects visible outside the Executor.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, Optional, Tuple

import yaml

from .models import ActionType, TaintState, TrustLevel


# ── ManifestProvenance ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ManifestProvenance:
    """
    Compile-time provenance record for a CompiledPolicy.

    Produced once by compile_world() and carried inside CompiledPolicy.
    Allows the runtime artifact to prove which manifest it was compiled from,
    and when, without re-reading the source file.

    Fields:
        workflow_id   : from manifest metadata.workflow_id, or "unknown"
        manifest_hash : sha256 hex digest of the raw manifest bytes
        compiled_at   : ISO-8601 UTC timestamp of when compile_world() ran
    """
    workflow_id: str
    manifest_hash: str
    compiled_at: str


# ── Module-private compile gate ───────────────────────────────────────────────
# This object is never exported. CompiledAction refuses construction without it.
# The only code that holds a reference to _COMPILE_GATE is compile_world().
_COMPILE_GATE: object = object()


# ── TaintRule ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TaintRule:
    """An immutable compiled taint rule."""
    taint: TaintState
    action_type: ActionType
    reason: str


# ── CompiledAction ────────────────────────────────────────────────────────────

class CompiledAction:
    """
    A sealed, immutable action descriptor produced by the compile phase.

    CompiledAction is PURE METADATA. It proves the action exists in the
    compiled world — it does NOT carry any callable handler or invocation
    capability. There is no _invoke(), no _handler, and no way to trigger
    execution from a CompiledAction reference.

    The only way to obtain a CompiledAction is from the CompiledPolicy
    returned by compile_world(). Attempting to construct one externally
    raises TypeError immediately — at object creation, not at execution.

    The existence of a CompiledAction object is proof that the action
    was present in world_manifest.yaml at compile time.
    """

    __slots__ = ("name", "action_type", "approval_required")

    def __init__(
        self,
        name: str,
        action_type: ActionType,
        approval_required: bool,
        _gate: object,
    ) -> None:
        if _gate is not _COMPILE_GATE:
            raise TypeError(
                "CompiledAction cannot be constructed outside the compile phase. "
                "Obtain actions from CompiledPolicy.actions."
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "action_type", action_type)
        object.__setattr__(self, "approval_required", approval_required)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("CompiledAction is immutable after construction")

    def __repr__(self) -> str:
        return f"CompiledAction({self.name!r}, type={self.action_type.value!r})"

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompiledAction):
            return NotImplemented
        return self.name == other.name


# ── CompiledPolicy ────────────────────────────────────────────────────────────

class CompiledPolicy:
    """
    Immutable compiled policy produced by compile_world().

    All fields are frozen after construction:
      - MappingProxyType: read-only dict view
      - frozenset: immutable by construction
      - tuple: immutable by construction

    All capability lookups are O(1) frozenset membership tests.
    No YAML parsing, no string iteration, no dynamic rule evaluation
    occurs after compile_world() returns.
    """

    __slots__ = ("_provenance", "_actions", "_capability_matrix", "_taint_rules", "_trust_map")

    def __init__(
        self,
        provenance: ManifestProvenance,
        actions: Dict[str, CompiledAction],
        capability_matrix: FrozenSet[Tuple[TrustLevel, ActionType]],
        taint_rules: Tuple[TaintRule, ...],
        trust_map: Dict[str, TrustLevel],
    ) -> None:
        object.__setattr__(self, "_provenance", provenance)
        object.__setattr__(self, "_actions", MappingProxyType(actions))
        object.__setattr__(self, "_capability_matrix", capability_matrix)
        object.__setattr__(self, "_taint_rules", taint_rules)
        object.__setattr__(self, "_trust_map", MappingProxyType(trust_map))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("CompiledPolicy is immutable after construction")

    # ── Provenance ────────────────────────────────────────────────────────────

    @property
    def provenance(self) -> ManifestProvenance:
        """Compile-time provenance: manifest hash, workflow_id, compiled_at."""
        return self._provenance

    # ── Action access (read-only proxy) ───────────────────────────────────────

    @property
    def actions(self) -> MappingProxyType:
        """Read-only view of compiled action descriptors. Cannot be mutated."""
        return self._actions

    def get_action(self, name: str) -> Optional[CompiledAction]:
        """Return the CompiledAction for name, or None if not in the ontology."""
        return self._actions.get(name)

    # ── Capability check (O(1) frozenset lookup) ──────────────────────────────

    def can_perform(self, trust_level: TrustLevel, action_type: ActionType) -> bool:
        """
        True iff (trust_level, action_type) is in the compiled capability matrix.

        This is an O(1) frozenset membership test. No string comparison.
        No loop. No YAML dict lookup. The matrix was compiled once and frozen.
        """
        return (trust_level, action_type) in self._capability_matrix

    # ── Taint rule lookup ─────────────────────────────────────────────────────

    def taint_rule_for(
        self, taint: TaintState, action_type: ActionType
    ) -> Optional[TaintRule]:
        """Return the first matching taint rule, or None."""
        for rule in self._taint_rules:
            if rule.taint is taint and rule.action_type is action_type:
                return rule
        return None

    # ── Trust resolution ──────────────────────────────────────────────────────

    def resolve_trust(self, channel_identity: str) -> TrustLevel:
        """
        Resolve a channel identity to its compiled TrustLevel.

        Fail-secure default: unknown identities resolve to UNTRUSTED.
        This is a compiled dict lookup — not a YAML string scan.
        """
        return self._trust_map.get(channel_identity, TrustLevel.UNTRUSTED)

    def __repr__(self) -> str:
        return (
            f"CompiledPolicy("
            f"workflow_id={self._provenance.workflow_id!r}, "
            f"manifest_hash={self._provenance.manifest_hash[:12]!r}, "
            f"actions={list(self._actions)})"
        )


# ── compile_world ─────────────────────────────────────────────────────────────

def compile_world(manifest_path: str) -> CompiledPolicy:
    """
    Compile phase entry point.

    Reads world_manifest.yaml exactly once. Produces an immutable
    CompiledPolicy containing pure metadata. After this function returns,
    the YAML file is not accessed again by any runtime component.
    """
    with open(manifest_path, "rb") as f:
        raw_bytes = f.read()

    raw = yaml.safe_load(raw_bytes)

    # ── Compute manifest provenance ───────────────────────────────────────────
    manifest_hash = hashlib.sha256(raw_bytes).hexdigest()
    workflow_id = raw.get("metadata", {}).get("workflow_id", "unknown")
    compiled_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    provenance = ManifestProvenance(
        workflow_id=workflow_id,
        manifest_hash=manifest_hash,
        compiled_at=compiled_at,
    )

    # ── Compile actions (metadata only — no handlers) ─────────────────────────
    actions: Dict[str, CompiledAction] = {}
    for name, cfg in raw["actions"].items():
        action_type = ActionType(cfg["type"])
        approval_required = bool(cfg.get("approval_required", False))
        actions[name] = CompiledAction(
            name=name,
            action_type=action_type,
            approval_required=approval_required,
            _gate=_COMPILE_GATE,
        )

    # ── Compile capability matrix → frozenset[(TrustLevel, ActionType)] ───────
    raw_capabilities: Dict[str, list] = raw.get("capabilities", {})
    capability_matrix: FrozenSet[Tuple[TrustLevel, ActionType]] = frozenset(
        (TrustLevel(trust_str), ActionType(action_type_str))
        for trust_str, action_type_strs in raw_capabilities.items()
        for action_type_str in action_type_strs
    )

    # ── Compile taint rules → tuple[TaintRule, ...] ───────────────────────────
    raw_taint_rules: list = raw.get("taint_rules", [])
    taint_rules: Tuple[TaintRule, ...] = tuple(
        TaintRule(
            taint=TaintState(rule["taint"]),
            action_type=ActionType(rule["action_type"]),
            reason=rule["reason"],
        )
        for rule in raw_taint_rules
    )

    # ── Compile trust map → MappingProxyType[str, TrustLevel] ────────────────
    raw_trust: Dict[str, str] = raw.get("trust", {})
    trust_map: Dict[str, TrustLevel] = {
        identity: TrustLevel(trust_str)
        for identity, trust_str in raw_trust.items()
    }

    return CompiledPolicy(
        provenance=provenance,
        actions=actions,
        capability_matrix=capability_matrix,
        taint_rules=taint_rules,
        trust_map=trust_map,
    )
