"""
emitter.py — Emit deterministic compiled artifacts from a validated World Manifest.

Each artifact is a standalone JSON file that the runtime can load without
parsing or interpreting the original YAML. The same manifest always produces
identical artifacts (determinism invariant).

Artifacts emitted:
  policy_table.json        — tool whitelist, forbidden patterns, budget limits
  capability_matrix.json   — trust_level → permitted side_effect categories
  taint_rules.json         — ordered taint propagation rules (human-readable)
  taint_state_machine.json — compiled taint state machine for O(1) runtime lookup
  escalation_table.json    — trigger conditions → decisions
  provenance_schema.json   — required/optional provenance fields + learning gate
  action_schemas.json      — per-action input schemas and metadata
  manifest_meta.json       — manifest identity for audit / reproducibility
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .taint_compiler import compile_from_manifest


def emit(manifest: dict, output_dir: Path) -> dict[str, Path]:
    """
    Write all compiled artifacts to output_dir.

    Returns a dict mapping artifact name → output path.
    All output is deterministic: same manifest → same files, same content.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    artifacts = {
        "policy_table.json": _build_policy_table(manifest),
        "capability_matrix.json": _build_capability_matrix(manifest),
        "taint_rules.json": _build_taint_rules(manifest),
        "taint_state_machine.json": compile_from_manifest(manifest),
        "escalation_table.json": _build_escalation_table(manifest),
        "provenance_schema.json": _build_provenance_schema(manifest),
        "action_schemas.json": _build_action_schemas(manifest),
        "manifest_meta.json": _build_manifest_meta(manifest),
    }

    for filename, data in artifacts.items():
        path = output_dir / filename
        # Sort keys for deterministic output
        content = json.dumps(data, indent=2, sort_keys=True) + "\n"
        path.write_text(content, encoding="utf-8")
        written[filename] = path

    return written


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------

def _build_policy_table(manifest: dict) -> dict:
    """
    Flat policy lookup table for the runtime evaluator.

    Contains: tool whitelist, forbidden patterns (from legacy field if present),
    per-tool budget limits, and global budget limits.
    """
    if manifest.get("version") == "2.0":
        actions = list(manifest.get("actions", {}).keys())
        irreversible_tools = [
            name for name, meta in manifest.get("actions", {}).items()
            if not meta.get("reversible", True)
        ]
    else:
        actions = [a["name"] for a in manifest.get("actions", [])]
        irreversible_tools = [
            a["name"] for a in manifest.get("actions", []) if not a.get("reversible", True)
        ]
        
    allowed_tools = sorted(actions)
    irreversible_tools = sorted(irreversible_tools)
    
    budgets = manifest.get("budgets", {})

    # Per-tool call limits from budgets.custom
    tool_limits: dict[str, int] = {}
    for entry in budgets.get("custom", []):
        tool_limits[entry["tool"]] = entry["max_calls"]

    return {
        "allowed_tools": allowed_tools,
        "irreversible_tools": irreversible_tools,
        "forbidden_patterns": manifest.get("forbidden_patterns", []),
        "budgets": {
            "max_actions_per_session": budgets.get("max_actions_per_session"),
            "max_external_reads": budgets.get("max_external_reads"),
            "max_external_writes": budgets.get("max_external_writes"),
            "max_tokens": budgets.get("max_tokens"),
            "max_session_duration_s": budgets.get("max_session_duration_s"),
            "tool_limits": tool_limits,
        },
    }


def _build_capability_matrix(manifest: dict) -> dict:
    """
    Trust level → set of permitted side_effect categories.

    Also includes a reverse index: side_effect → list of trust levels that permit it.
    """
    matrix = manifest.get("capability_matrix", {})

    # Normalise to sorted lists for determinism
    normalised: dict[str, list[str]] = {
        level: sorted(caps) for level, caps in matrix.items()
    }

    # Reverse index: side_effect → [trust levels]
    reverse: dict[str, list[str]] = {}
    for level, caps in normalised.items():
        for cap in caps:
            reverse.setdefault(cap, []).append(level)
    reverse = {k: sorted(v) for k, v in sorted(reverse.items())}

    return {
        "by_trust_level": normalised,
        "by_side_effect": reverse,
    }


def _build_taint_rules(manifest: dict) -> dict:
    """
    Ordered list of taint propagation rules.

    Each rule includes its id, source_taint, propagation steps, and
    sanitization gate (if any). Order is preserved from the manifest.
    """
    rules = manifest.get("taint_rules", [])
    compiled = []
    
    if manifest.get("version") == "2.0":
        for rule in rules:
            compiled.append({
                "source_taint": rule["source_taint"],
                "operation": rule["operation"],
                "result": rule["result"],
            })
    else:
        for rule in rules:
            compiled.append({
                "id": rule["id"],
                "description": rule.get("description", ""),
                "source_taint": rule["source_taint"],
                "propagation": [
                    {"operation": p["operation"], "spreads_to": p["spreads_to"]}
                    for p in rule.get("propagation", [])
                ],
                "sanitization_gate": rule.get("sanitization_gate"),
            })
    return {"rules": compiled}


def _build_escalation_table(manifest: dict) -> dict:
    """
    Flat lookup table for escalation decisions.

    Each entry maps a trigger pattern to a decision. The runtime evaluates
    these in order; the first matching trigger wins.
    """
    compiled = []
    if manifest.get("version") == "2.0":
        rules = manifest.get("escalation_rules", {})
        for name, rule in rules.items():
            # v2 format: { condition: "tainted", reason: "...", rule_id: "..." }
            # Wait, trigger is expected to be a dict by policy_eval.py!
            # If condition is "tainted", the trigger should be {"taint": True, "action_name": name}
            # policy_eval.py uses: _matches_escalation(trigger, tool, taint, trust_level)
            trigger: dict[str, Any] = {"action_name": name}
            if rule.get("condition") == "tainted":
                trigger["taint"] = True
                
            compiled.append({
                "id": rule.get("rule_id", name),
                "description": rule.get("reason", ""),
                "trigger": trigger,
                "decision": "deny", # default decision if not provided, or extract from rule if present. In v2 workspace it just blocks.
                "notify": rule.get("notify", []),
            })
    else:
        conditions = manifest.get("escalation_conditions", [])
        for cond in conditions:
            compiled.append({
                "id": cond["id"],
                "description": cond.get("description", ""),
                "trigger": cond["trigger"],
                "decision": cond["decision"],
                "notify": cond.get("notify", []),
            })
    return {"conditions": compiled}


def _build_provenance_schema(manifest: dict) -> dict:
    """
    Provenance field requirements and learning gate configuration.
    """
    schema = manifest.get("provenance_schema", {})
    return {
        "required_fields": sorted(schema.get("required_fields", [])),
        "optional_fields": sorted(schema.get("optional_fields", [])),
        "learning_gate": schema.get("learning_gate", {"requires_verified": True}),
    }


def _build_action_schemas(manifest: dict) -> dict:
    """
    Per-action metadata: input schema, output_trust, side_effects, reversibility.

    Keyed by action name for O(1) runtime lookup.
    """
    result: dict[str, Any] = {}
    
    if manifest.get("version") == "2.0":
        actions = manifest.get("actions", {})
        schemas = manifest.get("schemas", {})
        for name, meta in actions.items():
            result[name] = {
                "reversible": meta.get("reversible", True),
                "side_effects": sorted(meta.get("side_effects", [])),
                "output_trust": meta.get("output_trust", "SEMI_TRUSTED"),
                "input_schema": schemas.get(name),
            }
    else:
        actions_list = manifest.get("actions", [])
        for action in actions_list:
            name = action["name"]
            result[name] = {
                "reversible": action.get("reversible", True),
                "side_effects": sorted(action.get("side_effects", [])),
                "output_trust": action.get("output_trust", "SEMI_TRUSTED"),
                "input_schema": action.get("input_schema"),
            }
    return {"actions": result}


def _build_manifest_meta(manifest: dict) -> dict:
    """
    Identity record for reproducibility and audit.

    Includes manifest name/version and a content hash of the full manifest
    so that any change to the source produces a different artifact set.
    """
    if manifest.get("version") == "2.0":
        meta_name = manifest.get("name", "")
        meta_version = manifest.get("version", "2.0")
        meta_desc = manifest.get("description", "")
        meta_author = ""
    else:
        meta = manifest.get("manifest", {})
        meta_name = meta.get("name", "")
        meta_version = meta.get("version", "")
        meta_desc = meta.get("description", "")
        meta_author = meta.get("author", "")
        
    # Deterministic hash of the manifest content
    content_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "name": meta_name,
        "version": meta_version,
        "description": meta_desc,
        "author": meta_author,
        "content_hash": content_hash,
    }

