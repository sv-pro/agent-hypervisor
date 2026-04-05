"""
Agent Hypervisor — Core Framework
==================================
Implements manifest resolution, taint propagation, provenance tracking,
capability lookup, and invariant enforcement.

Zero dependency on Demo. No UI. No scenario-specific logic.
Interface: load a manifest, submit a proposed action, receive a decision.

This module could be replaced by a Rust implementation
without changing anything in demo.py.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import yaml
import json


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrustLevel(str, Enum):
    TRUSTED   = "trusted"
    UNTRUSTED = "untrusted"
    DERIVED   = "derived"   # inherited from provenance chain
    TAINTED   = "tainted"   # untrusted origin, propagated


class Decision(str, Enum):
    ALLOW = "allow"
    DENY  = "deny"
    ASK   = "ask"


class ExecutionMode(str, Enum):
    WORKFLOW    = "workflow"      # defining the world
    INTERACTIVE = "interactive"   # user present
    BACKGROUND  = "background"    # user absent


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ProvenanceRecord:
    """Full lineage of a data object."""
    source: str                          # original channel (email, user, web…)
    trust_level: TrustLevel
    session_id: str
    tainted: bool
    transformations: list[str] = field(default_factory=list)
    parent_ids: list[str] = field(default_factory=list)


@dataclass
class SemanticEvent:
    """
    Structured representation of an input.
    The agent only ever sees SemanticEvents — never raw text.
    """
    event_id: str
    source: str
    raw_payload: str
    sanitized_payload: str
    trust_level: TrustLevel
    tainted: bool
    provenance: ProvenanceRecord
    had_hidden_content: bool = False


@dataclass
class ProposedAction:
    """
    A structured request from the agent to affect the world.
    The agent cannot act directly — it proposes.
    """
    action_id: str
    action_type: str
    parameters: dict[str, Any]
    provenance_chain: list[ProvenanceRecord]
    agent_reasoning: str = ""   # why the agent wants this (for ASK display)


@dataclass
class ResolutionResult:
    """
    Output of manifest resolution. Always one of: ALLOW, DENY, ASK.
    Fully deterministic: same manifest + same input → same result.
    """
    decision: Decision
    rule_triggered: str
    reason: str
    provenance_summary: str
    action: ProposedAction


# ---------------------------------------------------------------------------
# Invariants — physics laws, cannot be overridden by manifest
# ---------------------------------------------------------------------------

class InvariantViolation(Exception):
    def __init__(self, law: str, reason: str):
        self.law = law
        self.reason = reason
        super().__init__(f"{law}: {reason}")


def check_invariants(action: ProposedAction, manifest: "WorldManifest") -> None:
    """
    Evaluate all invariants before manifest lookup.
    Raises InvariantViolation on first breach.
    """
    action_def = manifest.actions.get(action.action_type)
    required_caps = action_def.get("requires", []) if action_def else []

    # TaintContainmentLaw
    is_tainted = any(p.tainted for p in action.provenance_chain)
    if is_tainted and "external_side_effects" in required_caps:
        raise InvariantViolation(
            "TaintContainmentLaw",
            "Tainted data cannot trigger external_side_effects. "
            "This action does not exist in a world containing tainted data."
        )

    # ProvenanceLaw
    if action.action_type == "write_memory":
        if not action.provenance_chain:
            raise InvariantViolation(
                "ProvenanceLaw",
                "memory_write requires provenance metadata. "
                "Write rejected: no provenance chain provided."
            )


# ---------------------------------------------------------------------------
# World Manifest
# ---------------------------------------------------------------------------

class WorldManifest:
    """
    Formal specification of everything that exists in the agent's universe.
    Loaded from YAML. Compiled into lookup structures.
    No LLM involved at runtime.
    """

    def __init__(self, data: dict):
        self.name: str = data.get("name", "unnamed")
        self.version: str = data.get("version", "1.0")

        self.trust_channels: dict[str, str] = data.get("trust_channels", {})
        self.capabilities: dict[str, list[str]] = data.get("capabilities", {})
        self.actions: dict[str, dict] = data.get("actions", {})
        self.invariants: list[str] = data.get("invariants", [])

        # explicit allow/deny rules
        self.explicit_rules: dict[str, str] = data.get("explicit_rules", {})

    @classmethod
    def from_yaml(cls, path: str) -> "WorldManifest":
        with open(path) as f:
            return cls(yaml.safe_load(f))

    @classmethod
    def from_dict(cls, data: dict) -> "WorldManifest":
        return cls(data)

    def resolve_trust(self, source: str) -> TrustLevel:
        raw = self.trust_channels.get(source, "untrusted")
        return TrustLevel(raw)

    def get_capabilities(self, trust_level: TrustLevel, tainted: bool) -> list[str]:
        if tainted:
            return self.capabilities.get("tainted", [])
        return self.capabilities.get(trust_level.value, [])

    def action_exists(self, action_type: str) -> bool:
        return action_type in self.actions

    def extend(self, action_type: str, requires: list[str]) -> "WorldManifest":
        """Return a new manifest with an added action. Immutable update."""
        import copy
        new_data = {
            "name": self.name,
            "version": self.version,
            "trust_channels": copy.deepcopy(self.trust_channels),
            "capabilities": copy.deepcopy(self.capabilities),
            "actions": copy.deepcopy(self.actions),
            "invariants": list(self.invariants),
            "explicit_rules": copy.deepcopy(self.explicit_rules),
        }
        new_data["actions"][action_type] = {"requires": requires}
        return WorldManifest(new_data)


# ---------------------------------------------------------------------------
# Manifest Resolution Engine
# ---------------------------------------------------------------------------

class ManifestResolver:
    """
    Deterministic resolution of a ProposedAction against a WorldManifest.

    Resolution order:
      1. Invariant check (physics — cannot be overridden)
      2. Explicit deny rule
      3. Explicit allow rule
      4. Capability check (action requires caps not present in trust level)
      5. Action not in manifest → ASK or DENY depending on mode
    """

    def resolve(
        self,
        action: ProposedAction,
        manifest: WorldManifest,
        mode: ExecutionMode,
        effective_trust: TrustLevel,
        is_tainted: bool,
    ) -> ResolutionResult:

        provenance_summary = self._summarize_provenance(action.provenance_chain)

        # Step 1: Invariants
        try:
            check_invariants(action, manifest)
        except InvariantViolation as e:
            return ResolutionResult(
                decision=Decision.DENY,
                rule_triggered=e.law,
                reason=e.reason,
                provenance_summary=provenance_summary,
                action=action,
            )

        # Step 2: Explicit deny
        if manifest.explicit_rules.get(action.action_type) == "deny":
            return ResolutionResult(
                decision=Decision.DENY,
                rule_triggered="ExplicitDeny",
                reason=f"Action '{action.action_type}' is explicitly denied in this world.",
                provenance_summary=provenance_summary,
                action=action,
            )

        # Step 3: Explicit allow
        if manifest.explicit_rules.get(action.action_type) == "allow":
            return ResolutionResult(
                decision=Decision.ALLOW,
                rule_triggered="ExplicitAllow",
                reason=f"Action '{action.action_type}' is explicitly allowed.",
                provenance_summary=provenance_summary,
                action=action,
            )

        # Step 4: Capability check
        if manifest.action_exists(action.action_type):
            action_def = manifest.actions[action.action_type]
            required_caps = action_def.get("requires", [])
            available_caps = manifest.get_capabilities(effective_trust, is_tainted)

            missing = [c for c in required_caps if c not in available_caps]
            if missing:
                return ResolutionResult(
                    decision=Decision.DENY,
                    rule_triggered="CapabilityBoundaryLaw",
                    reason=(
                        f"Action '{action.action_type}' requires capabilities {missing}, "
                        f"which are absent at trust level '{effective_trust.value}'"
                        + (" (tainted)" if is_tainted else "") + "."
                    ),
                    provenance_summary=provenance_summary,
                    action=action,
                )
            # All capabilities present — allow
            return ResolutionResult(
                decision=Decision.ALLOW,
                rule_triggered="CapabilityCheck",
                reason=f"All required capabilities present. Action '{action.action_type}' allowed.",
                provenance_summary=provenance_summary,
                action=action,
            )

        # Step 5: Action not in manifest (manifest gap)
        if mode == ExecutionMode.BACKGROUND:
            return ResolutionResult(
                decision=Decision.DENY,
                rule_triggered="ManifestGap_Background",
                reason=(
                    f"Action '{action.action_type}' is not covered by this manifest. "
                    "Background mode: uncovered actions are denied."
                ),
                provenance_summary=provenance_summary,
                action=action,
            )
        else:
            return ResolutionResult(
                decision=Decision.ASK,
                rule_triggered="ManifestGap_Interactive",
                reason=(
                    f"Action '{action.action_type}' is not covered by this manifest. "
                    "User approval required: approve once or extend the world."
                ),
                provenance_summary=provenance_summary,
                action=action,
            )

    def _summarize_provenance(self, chain: list[ProvenanceRecord]) -> str:
        if not chain:
            return "no provenance"
        parts = []
        for p in chain:
            t = "tainted" if p.tainted else p.trust_level.value
            parts.append(f"{p.source}[{t}, session={p.session_id}]")
        return " → ".join(parts)


# ---------------------------------------------------------------------------
# Hypervisor — public interface
# ---------------------------------------------------------------------------

class Hypervisor:
    """
    Public interface for the Agent Hypervisor core.
    This is the only class Demo should instantiate.
    """

    def __init__(self, manifest: WorldManifest, mode: ExecutionMode):
        self.manifest = manifest
        self.mode = mode
        self._resolver = ManifestResolver()

    def virtualize_input(
        self,
        event_id: str,
        source: str,
        raw_payload: str,
        session_id: str = "s1",
    ) -> SemanticEvent:
        """
        Transform raw input into a SemanticEvent.
        Sanitizes payload, assigns trust, computes taint.
        """
        trust_level = self.manifest.resolve_trust(source)

        # Sanitize: strip zero-width chars and [[HIDDEN]] patterns
        import re
        sanitized = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", raw_payload)
        sanitized, n_hidden = re.subn(r"\[\[.*?\]\]", "", sanitized)
        had_hidden = n_hidden > 0
        sanitized = sanitized.strip()

        tainted = (trust_level != TrustLevel.TRUSTED) or had_hidden

        provenance = ProvenanceRecord(
            source=source,
            trust_level=trust_level,
            session_id=session_id,
            tainted=tainted,
        )

        return SemanticEvent(
            event_id=event_id,
            source=source,
            raw_payload=raw_payload,
            sanitized_payload=sanitized,
            trust_level=trust_level,
            tainted=tainted,
            provenance=provenance,
            had_hidden_content=had_hidden,
        )

    def evaluate(
        self,
        action: ProposedAction,
    ) -> ResolutionResult:
        """
        Evaluate a ProposedAction against the current manifest and mode.
        Returns a fully deterministic ResolutionResult.
        """
        # Compute effective trust and taint from provenance chain
        is_tainted = any(p.tainted for p in action.provenance_chain)

        if is_tainted:
            effective_trust = TrustLevel.TAINTED
        elif action.provenance_chain:
            effective_trust = action.provenance_chain[-1].trust_level
        else:
            effective_trust = TrustLevel.TRUSTED

        return self._resolver.resolve(
            action=action,
            manifest=self.manifest,
            mode=self.mode,
            effective_trust=effective_trust,
            is_tainted=is_tainted,
        )

    def extend_manifest(self, action_type: str, requires: list[str]) -> None:
        """
        Extend the world manifest with a new action definition.
        Called after user chooses 'manifest extension' in ASK dialog.
        """
        self.manifest = self.manifest.extend(action_type, requires)
