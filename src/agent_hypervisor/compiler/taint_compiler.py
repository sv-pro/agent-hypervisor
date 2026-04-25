"""
taint_compiler.py — Compile taint propagation rules into a runtime state machine.

The emitter (emitter.py) writes taint_rules.json as a human-readable ordered
list. This module compiles that list into taint_state_machine.json — a set of
flat lookup tables the runtime can use without iterating over rules:

  transition_table  : {source_taint → {operation → {spreads_to, taint_label}}}
  containment_rules : {taint_label → {target_type → gate_required | "BLOCK"}}
  sanitization_index: {taint_label → {requires, log_entry}}
  taint_order       : [labels from most → least restrictive]

Design invariant: the state machine is deterministic. The same taint_rules input
always produces the same state machine. Order of rules in the manifest controls
priority when two rules would match the same (source_taint, operation) pair —
first rule wins (logged as a warning, not an error).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Taint levels ordered from most to least restrictive.
# UNTRUSTED dominates SEMI_TRUSTED dominates TRUSTED in propagation.
TAINT_ORDER = ["UNTRUSTED", "SEMI_TRUSTED", "TRUSTED"]

# Default containment: which (taint_label, spreads_to) combinations are
# blocked at Layer 5 without a sanitization gate. "BLOCK" = hard deny.
# These defaults apply when the manifest does not specify a sanitization gate.
_DEFAULT_CONTAINMENT: dict[str, dict[str, str]] = {
    "UNTRUSTED": {
        "output": "BLOCK",
        "memory_entry": "BLOCK",
        "execution_input": "BLOCK",
    },
    "SEMI_TRUSTED": {
        "output": "schema_validation",
        "memory_entry": "schema_validation",
        "execution_input": "human_approval",
    },
}


def compile_taint_rules(taint_rules: list[dict]) -> dict:
    """
    Compile an ordered list of taint rules into runtime state machine tables.

    Args:
        taint_rules: the ``rules`` list from taint_rules.json

    Returns:
        A dict ready to be serialised as taint_state_machine.json
    """
    transition_table: dict[str, dict[str, dict[str, Any]]] = {}
    sanitization_index: dict[str, dict[str, Any]] = {}
    containment_rules: dict[str, dict[str, str]] = {}
    conflicts: list[str] = []

    for rule in taint_rules:
        source_taint = rule["source_taint"]
        rule_id = rule["id"]
        gate = rule.get("sanitization_gate")

        # Build sanitization index
        if gate and source_taint not in sanitization_index:
            sanitization_index[source_taint] = {
                "requires": gate.get("requires"),
                "log_entry": gate.get("log_entry", False),
            }

        # Build transition table: (source_taint, operation) → entry
        transitions = transition_table.setdefault(source_taint, {})
        for prop in rule.get("propagation", []):
            operation = prop["operation"]
            spreads_to = prop["spreads_to"]

            if operation in transitions:
                # First rule wins; record conflict for audit
                existing_rule = transitions[operation].get("_rule_id", "?")
                conflicts.append(
                    f"Conflict: ({source_taint}, {operation}) defined in "
                    f"rule '{existing_rule}' and '{rule_id}' — first wins."
                )
                continue

            # Determine gate for this specific spread target
            if gate:
                target_gate = gate.get("requires", "BLOCK")
            else:
                # Fall back to defaults
                taint_defaults = _DEFAULT_CONTAINMENT.get(source_taint, {})
                target_gate = taint_defaults.get(spreads_to, "BLOCK")

            transitions[operation] = {
                "spreads_to": spreads_to,
                "taint_label": source_taint,
                "gate_required": target_gate,
                "_rule_id": rule_id,
            }

        # Build containment rules for this taint label
        if source_taint not in containment_rules:
            containment_rules[source_taint] = {}
        for prop in rule.get("propagation", []):
            spreads_to = prop["spreads_to"]
            if spreads_to not in containment_rules[source_taint]:
                if gate:
                    containment_rules[source_taint][spreads_to] = gate.get("requires", "BLOCK")
                else:
                    taint_defaults = _DEFAULT_CONTAINMENT.get(source_taint, {})
                    containment_rules[source_taint][spreads_to] = taint_defaults.get(
                        spreads_to, "BLOCK"
                    )

    # Remove internal _rule_id keys from the serialised output
    clean_transitions: dict[str, dict[str, dict[str, Any]]] = {}
    for taint_label, ops in transition_table.items():
        clean_transitions[taint_label] = {
            op: {k: v for k, v in entry.items() if k != "_rule_id"}
            for op, entry in ops.items()
        }

    # Merge in default containment for any taint labels not covered by rules
    full_containment = dict(_DEFAULT_CONTAINMENT)
    for label, targets in containment_rules.items():
        full_containment.setdefault(label, {}).update(targets)

    return {
        "taint_order": TAINT_ORDER,
        "transition_table": clean_transitions,
        "containment_rules": full_containment,
        "sanitization_index": sanitization_index,
        "conflicts": conflicts,
    }


def compile_from_manifest(manifest: dict) -> dict:
    """Compile taint rules directly from a parsed manifest dict."""
    if manifest.get("version") == "2.0":
        return compile_v2_taint_machine(manifest)
    rules = manifest.get("taint_rules", [])
    return compile_taint_rules(rules)


def compile_v2_taint_machine(manifest: dict) -> dict:
    """Compile v2 data_classes and transition_policies into the runtime state machine.

    Translates:
      - ``taint_rules`` (flat [{source_taint, operation, result}]) into the
        ``transition_table`` used by the runtime for O(1) propagation lookup.
      - Zone→Zone ``transition_policies`` + ``side_effect_surfaces`` into
        TrustLevel→SideEffect ``containment_rules``.
      - ``data_classes`` into the ``sanitization_index``.
    """
    data_classes = manifest.get("data_classes", {})
    transition_policies = manifest.get("transition_policies", [])
    side_effect_surfaces = manifest.get("side_effect_surfaces", [])
    actions = manifest.get("actions", {})
    trust_zones = manifest.get("trust_zones", {})
    taint_rules = manifest.get("taint_rules", [])

    # 1. Build transition_table from flat taint_rules
    #    Each rule: {source_taint, operation, result: preserve|clear}
    #    'preserve' means taint flows through → downstream use must be gated.
    #    'clear'    means taint is explicitly sanitised → gate is 'auto'.
    transition_table: dict[str, dict[str, dict]] = {}
    for rule in taint_rules:
        source_taint = rule.get("source_taint")
        operation = rule.get("operation")
        result = rule.get("result", "preserve")
        if not source_taint or not operation:
            continue
        gate = "BLOCK" if result == "preserve" else "auto"
        transition_table.setdefault(source_taint, {})[operation] = {
            "spreads_to": "output",
            "taint_label": source_taint,
            "gate_required": gate,
        }

    # 2. Build sanitization index from data classes
    sanitization_index: dict[str, dict[str, Any]] = {}
    for dc_name, dc_meta in data_classes.items():
        if not isinstance(dc_meta, dict):
            continue
        label = dc_meta.get("taint_label", dc_name)
        confirmation = dc_meta.get("confirmation", "hard_confirm")
        sanitization_index[label] = {
            "requires": confirmation,
            "log_entry": True,
        }

    # 3. Build containment rules: trust_level → side_effect → gate
    #    Start with defaults and overlay transition_policy decisions.
    containment_rules: dict[str, dict[str, str]] = dict(_DEFAULT_CONTAINMENT)
    for level in TAINT_ORDER:
        containment_rules.setdefault(level, {})

    for policy in transition_policies:
        from_zone = policy.get("from_zone")
        to_zone = policy.get("to_zone")

        from_trust = trust_zones.get(from_zone, {}).get("default_trust") if isinstance(trust_zones.get(from_zone), dict) else None
        if not from_trust:
            continue

        if not policy.get("allowed", False):
            gate = policy.get("confirmation", "BLOCK")
            if gate == "auto":
                gate = "BLOCK"  # disallowed transition stays blocked even if confirmation is auto
        else:
            gate = policy.get("confirmation", "auto")

        # Find all actions that touch the to_zone via side_effect_surfaces
        for surface in side_effect_surfaces:
            if not isinstance(surface, dict):
                continue
            if to_zone in surface.get("touches", []):
                action_name = surface.get("action")
                action_meta = actions.get(action_name, {})
                if not isinstance(action_meta, dict):
                    continue
                for se in action_meta.get("side_effects", []):
                    containment_rules[from_trust][se] = gate

    return {
        "taint_order": TAINT_ORDER,
        "transition_table": transition_table,
        "containment_rules": containment_rules,
        "sanitization_index": sanitization_index,
        "conflicts": [],
    }


def emit_state_machine(manifest: dict, output_dir: Path) -> Path:
    """
    Write taint_state_machine.json to output_dir.

    Returns the path of the written file.
    """
    state_machine = compile_from_manifest(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "taint_state_machine.json"
    path.write_text(json.dumps(state_machine, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
