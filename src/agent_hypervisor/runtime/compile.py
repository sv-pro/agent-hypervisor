"""
Compile Phase
=============

Transforms world_manifest.yaml into an immutable CompiledPolicy.

This runs ONCE at startup via build_runtime(). After compilation:
  - world_manifest.yaml is not accessed by any runtime component
  - All policy decisions live in frozen Python data structures
  - No string comparisons, no YAML parsing, no dict iteration at request time

Compile outputs:
  action_space:      frozenset[str]
                     The closed action set. These and only these actions exist
                     in this compiled world. Membership test is O(1).
  actions:           MappingProxyType[str, CompiledAction]
                     Sealed — CallerCode cannot add or modify entries.
  capability_matrix: frozenset[tuple[TrustLevel, ActionType]]
                     O(1) membership test — no loops, no strings.
  taint_rules:       tuple[TaintRule, ...]
                     Immutable ordered sequence.
  trust_map:         MappingProxyType[str, TrustLevel]
                     Channel identity → TrustLevel, resolved at IR build time.
  provenance_rules:  tuple[CompiledProvenanceRule, ...]
                     Compiled provenance decision structure.

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

from .models import ActionType, ArgumentProvenance, ProvenanceVerdict, TaintState, TrustLevel


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


# ── CompiledProvenanceRule ────────────────────────────────────────────────────

@dataclass(frozen=True)
class CompiledProvenanceRule:
    """
    One compiled provenance rule from the world manifest.

    Replaces a YAML dict entry that would otherwise be interpreted at runtime.
    All fields are typed enums produced at compile_world() time; no string
    comparison or enum construction occurs after compilation.

    Matching semantics:
        tool       : "*" matches any tool name, otherwise exact match
        argument   : None means the rule applies to the whole call
                     (not to a specific argument); otherwise exact match
        provenance : None means any provenance; otherwise the ArgumentProvenance
                     must appear somewhere in the argument's provenance chain
        verdict    : the verdict to return if this rule matches

    Verdict precedence (highest wins across all matching rules):
        deny (2) > ask (1) > allow (0)

    Fail-closed default: if no rule matches, evaluate_provenance() returns deny.
    """
    rule_id: str
    tool: str
    verdict: ProvenanceVerdict
    argument: Optional[str] = None
    provenance: Optional[ArgumentProvenance] = None


# Precedence table used by evaluate_provenance — module-level constant.
_VERDICT_PRECEDENCE: dict[str, int] = {"deny": 2, "ask": 1, "allow": 0}


def _provenance_rule_matches(
    rule: CompiledProvenanceRule,
    tool: str,
    argument: Optional[str],
    chain_provenances: FrozenSet[ArgumentProvenance],
) -> bool:
    """
    Return True if the compiled rule applies to (tool, argument, chain).

    Module-private helper so CompiledPolicy.evaluate_provenance() stays
    readable. Contains no I/O, no string-to-enum construction, no YAML access.
    """
    # Tool filter
    if rule.tool != "*" and rule.tool != tool:
        return False

    # Argument + provenance filter
    if rule.argument is not None:
        # Rule targets a specific argument: caller must have provided that argument.
        if argument != rule.argument:
            return False
        # If the rule also filters on a provenance class, that class must appear
        # somewhere in the argument's provenance chain.
        if rule.provenance is not None and rule.provenance not in chain_provenances:
            return False

    return True


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

    __slots__ = (
        "_provenance",
        "_action_space",
        "_actions",
        "_capability_matrix",
        "_taint_rules",
        "_trust_map",
        "_provenance_rules",
    )

    def __init__(
        self,
        provenance: ManifestProvenance,
        actions: Dict[str, CompiledAction],
        capability_matrix: FrozenSet[Tuple[TrustLevel, ActionType]],
        taint_rules: Tuple[TaintRule, ...],
        trust_map: Dict[str, TrustLevel],
        provenance_rules: Tuple["CompiledProvenanceRule", ...] = (),
    ) -> None:
        object.__setattr__(self, "_provenance", provenance)
        object.__setattr__(self, "_action_space", frozenset(actions.keys()))
        object.__setattr__(self, "_actions", MappingProxyType(actions))
        object.__setattr__(self, "_capability_matrix", capability_matrix)
        object.__setattr__(self, "_taint_rules", taint_rules)
        object.__setattr__(self, "_trust_map", MappingProxyType(trust_map))
        object.__setattr__(self, "_provenance_rules", provenance_rules)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("CompiledPolicy is immutable after construction")

    # ── Closed action set ─────────────────────────────────────────────────────

    @property
    def action_space(self) -> FrozenSet[str]:
        """
        The closed action set of this compiled world.

        Contains exactly the names of actions declared in the world manifest.
        These and only these actions exist — any name absent from this set
        is impossible in this world, not merely denied.

        This is the canonical existence boundary. Downstream checks
        (IRBuilder, worker registry assertion) should derive existence from
        this set, not from len(actions) or actions.keys().

        O(1) membership test:
            if action_name in policy.action_space: ...
        """
        return self._action_space

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

    # ── Provenance rule evaluation ────────────────────────────────────────────

    @property
    def provenance_rules(self) -> Tuple["CompiledProvenanceRule", ...]:
        """Immutable tuple of compiled provenance rules. Read-only."""
        return self._provenance_rules

    def evaluate_provenance(
        self,
        tool: str,
        argument: Optional[str] = None,
        chain_provenances: FrozenSet[ArgumentProvenance] = frozenset(),
    ) -> ProvenanceVerdict:
        """
        Evaluate compiled provenance rules for a (tool, argument, chain) triple.

        Returns the highest-precedence verdict among all matching rules.
        Returns ProvenanceVerdict.deny if no rules match — fail-closed default.

        This method operates entirely on compiled data structures.
        No YAML parsing, no file access, no string-to-enum construction.

        Args:
            tool:             the tool name being requested
            argument:         the specific argument being evaluated, or None for
                              a whole-call (tool-level) evaluation
            chain_provenances: the set of provenance classes present anywhere in
                              the argument's value provenance chain
        """
        best: Optional[ProvenanceVerdict] = None
        best_prec = -1

        for rule in self._provenance_rules:
            if not _provenance_rule_matches(rule, tool, argument, chain_provenances):
                continue
            prec = _VERDICT_PRECEDENCE.get(rule.verdict.value, 0)
            if prec > best_prec:
                best = rule.verdict
                best_prec = prec

        return best if best is not None else ProvenanceVerdict.deny

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
            f"action_space={sorted(self._action_space)}, "
            f"provenance_rules={len(self._provenance_rules)})"
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

    # ── Compile provenance rules → tuple[CompiledProvenanceRule, ...] ─────────
    # Source: manifest provenance_rules section.
    # Absent section → empty tuple → evaluate_provenance() is fail-closed (deny).
    raw_provenance_rules: list = raw.get("provenance_rules", [])
    provenance_rules: Tuple[CompiledProvenanceRule, ...] = tuple(
        CompiledProvenanceRule(
            rule_id=r.get("id", f"rule-{i:03d}"),
            tool=r.get("tool", "*"),
            verdict=ProvenanceVerdict(r["verdict"]),
            argument=r.get("argument"),
            provenance=ArgumentProvenance(r["provenance"]) if r.get("provenance") else None,
        )
        for i, r in enumerate(raw_provenance_rules)
    )

    return CompiledPolicy(
        provenance=provenance,
        actions=actions,
        capability_matrix=capability_matrix,
        taint_rules=taint_rules,
        trust_map=trust_map,
        provenance_rules=provenance_rules,
    )
