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
    rules = manifest.get("taint_rules", [])
    return compile_taint_rules(rules)


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
