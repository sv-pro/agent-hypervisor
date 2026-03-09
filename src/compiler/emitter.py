"""
emitter.py — Emit deterministic compiled artifacts from a validated World Manifest.

Each artifact is a standalone JSON file that the runtime can load without
parsing or interpreting the original YAML. The same manifest always produces
identical artifacts (determinism invariant).

Artifacts emitted:
  policy_table.json        — tool whitelist, forbidden patterns, budget limits
  capability_matrix.json   — trust_level → permitted side_effect categories
  taint_rules.json         — ordered taint propagation rules
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
    actions = manifest.get("actions", [])
    budgets = manifest.get("budgets", {})

    allowed_tools = sorted(a["name"] for a in actions)

    # Per-tool call limits from budgets.custom
    tool_limits: dict[str, int] = {}
    for entry in budgets.get("custom", []):
        tool_limits[entry["tool"]] = entry["max_calls"]

    # Irreversible tools — runtime uses this for quick reversibility check
    irreversible_tools = sorted(
        a["name"] for a in actions if not a.get("reversible", True)
    )

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
    conditions = manifest.get("escalation_conditions", [])
    compiled = []
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
    actions = manifest.get("actions", [])
    result: dict[str, Any] = {}
    for action in actions:
        name = action["name"]
        result[name] = {
            "reversible": action["reversible"],
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
    meta = manifest.get("manifest", {})
    # Deterministic hash of the manifest content
    content_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "name": meta.get("name", ""),
        "version": meta.get("version", ""),
        "description": meta.get("description", ""),
        "author": meta.get("author", ""),
        "content_hash": content_hash,
    }
