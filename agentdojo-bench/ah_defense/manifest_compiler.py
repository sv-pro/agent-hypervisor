"""
manifest_compiler.py — Load and compile fail-closed manifest v2 into runtime structures.

INV-002: Missing or invalid manifest => deny everything.
INV-009: Same manifest + same input => same decision (compiled artifact is immutable).
INV-012: Actions not defined in ontology do not exist.

No permissive defaults. Invalid manifest raises ManifestCompileError.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ah_defense.policy_types import (
    ActionDefinition,
    CompiledManifest,
)


class ManifestCompileError(Exception):
    """Raised when a manifest cannot be loaded or compiled.

    Callers must treat this as a hard deny signal (INV-002).
    """


# ── Public API ────────────────────────────────────────────────────────────────

def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load and structurally validate a manifest YAML file.

    Args:
        path: Filesystem path to the manifest YAML.

    Returns:
        Raw dict from YAML.

    Raises:
        ManifestCompileError: If file is missing, unreadable, or structurally invalid.
    """
    path = Path(path)
    if not path.exists():
        raise ManifestCompileError(f"Manifest file not found: {path}")

    try:
        with path.open() as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ManifestCompileError(f"YAML parse error in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestCompileError(f"Manifest root must be a mapping, got {type(raw).__name__}")

    _validate_raw_manifest(raw, path)
    return raw


def compile_manifest(raw: dict[str, Any]) -> CompiledManifest:
    """Compile a raw manifest dict into an immutable CompiledManifest.

    Raises:
        ManifestCompileError: On any structural or semantic error.
    """
    version = raw.get("version", "")
    if not version:
        raise ManifestCompileError("Manifest missing 'version' field")

    suite = raw.get("suite", "")
    if not suite:
        raise ManifestCompileError("Manifest missing 'suite' field")

    actions = _compile_actions(raw)
    tool_predicates = _compile_predicates(raw, actions)
    capability_matrix = _compile_capability_matrix(raw)
    taint_rules = _compile_taint_rules(raw)
    escalation_rules = _compile_escalation_rules(raw)

    channels_raw = raw.get("trust_channels", {})
    inter_agent_trust = "untrusted"
    if isinstance(channels_raw, dict) and "agent" in channels_raw:
        inter_agent_trust = channels_raw["agent"].get("trust_level", "untrusted")

    return CompiledManifest(
        version=version,
        suite=suite,
        actions=actions,
        tool_predicates=tool_predicates,
        capability_matrix=capability_matrix,
        taint_rules=taint_rules,
        escalation_rules=escalation_rules,
        inter_agent_trust=inter_agent_trust,
    )


def load_and_compile(path: str | Path) -> CompiledManifest:
    """Convenience: load_manifest + compile_manifest in one call.

    Raises:
        ManifestCompileError: If either step fails.
    """
    raw = load_manifest(path)
    return compile_manifest(raw)


def resolve_action_definition(
    manifest: CompiledManifest,
    action_name: str,
) -> ActionDefinition | None:
    """Return the ActionDefinition for action_name, or None if not in ontology.

    INV-001/INV-012: caller must treat None as deny.
    """
    return manifest.actions.get(action_name)


def get_schema_for_action(
    manifest: CompiledManifest,
    action_name: str,
) -> dict[str, Any] | None:
    """Return the parameter schema for action_name, or None if not found."""
    defn = manifest.actions.get(action_name)
    if defn is None:
        return None
    return defn.schema


def get_capabilities_for_trust(
    manifest: CompiledManifest,
    trust_level: str,
) -> frozenset[str]:
    """Return the capability set for a given trust level.

    Returns empty frozenset if trust_level is not in the matrix (conservative).
    """
    return manifest.capability_matrix.get(trust_level, frozenset())


# ── Internal compilers ────────────────────────────────────────────────────────

_VALID_ACTION_CLASSES = frozenset({
    "read_only",
    "reversible_internal",
    "irreversible_internal",
    "external_boundary",
})

_VALID_RISK_CLASSES = frozenset({"low", "medium", "high", "critical"})


def _validate_raw_manifest(raw: dict[str, Any], path: Path) -> None:
    required_sections = ("version", "suite", "actions", "trust_channels", "capabilities", "predicates")
    missing = [s for s in required_sections if s not in raw]
    if missing:
        raise ManifestCompileError(
            f"Manifest {path} missing required sections: {missing}"
        )


def _compile_actions(raw: dict[str, Any]) -> dict[str, ActionDefinition]:
    actions_raw = raw.get("actions", {})
    schemas_raw = raw.get("schemas", {})

    if not isinstance(actions_raw, dict) or not actions_raw:
        raise ManifestCompileError("Manifest 'actions' section is empty or not a mapping")

    result: dict[str, ActionDefinition] = {}

    for name, cfg in actions_raw.items():
        if not isinstance(cfg, dict):
            raise ManifestCompileError(f"Action '{name}' definition must be a mapping")

        action_class = cfg.get("action_class", "")
        if action_class not in _VALID_ACTION_CLASSES:
            raise ManifestCompileError(
                f"Action '{name}': invalid action_class '{action_class}'"
                f" (valid: {sorted(_VALID_ACTION_CLASSES)})"
            )

        risk_class = cfg.get("risk_class", "")
        if risk_class not in _VALID_RISK_CLASSES:
            raise ManifestCompileError(
                f"Action '{name}': invalid risk_class '{risk_class}'"
                f" (valid: {sorted(_VALID_RISK_CLASSES)})"
            )

        caps = cfg.get("required_capabilities", [])
        if not isinstance(caps, list):
            raise ManifestCompileError(f"Action '{name}': required_capabilities must be a list")

        schema = schemas_raw.get(name, {})
        if not isinstance(schema, dict):
            schema = {}

        result[name] = ActionDefinition(
            name=name,
            action_class=action_class,  # type: ignore[arg-type]
            risk_class=risk_class,       # type: ignore[arg-type]
            required_capabilities=tuple(caps),
            schema=schema,
            requires_approval=bool(cfg.get("requires_approval", False)),
            taint_passthrough=bool(cfg.get("taint_passthrough", True)),
            irreversible=bool(cfg.get("irreversible", False)),
            external_boundary=bool(cfg.get("external_boundary", False)),
            description=str(cfg.get("description", "")),
        )

    return result


def _compile_predicates(
    raw: dict[str, Any],
    actions: dict[str, ActionDefinition],
) -> dict[str, list[dict[str, Any]]]:
    """Compile tool_name -> ordered predicate list.

    Each predicate must reference an existing action.
    """
    preds_raw = raw.get("predicates", {})
    if not isinstance(preds_raw, dict):
        raise ManifestCompileError("Manifest 'predicates' section must be a mapping")

    result: dict[str, list[dict[str, Any]]] = {}

    for tool_name, pred_list in preds_raw.items():
        if not isinstance(pred_list, list):
            raise ManifestCompileError(
                f"Predicates for tool '{tool_name}' must be a list"
            )
        compiled_preds: list[dict[str, Any]] = []
        for i, pred in enumerate(pred_list):
            if not isinstance(pred, dict):
                raise ManifestCompileError(
                    f"Predicate {i} for tool '{tool_name}' must be a mapping"
                )
            target_action = pred.get("action", "")
            if not target_action:
                raise ManifestCompileError(
                    f"Predicate {i} for tool '{tool_name}' missing 'action'"
                )
            if target_action not in actions:
                raise ManifestCompileError(
                    f"Predicate {i} for tool '{tool_name}' references undefined action"
                    f" '{target_action}'"
                )
            match_cfg = pred.get("match", {})
            if not isinstance(match_cfg, dict):
                raise ManifestCompileError(
                    f"Predicate {i} for tool '{tool_name}': 'match' must be a mapping"
                )
            compiled_preds.append({
                "action": target_action,
                "match": match_cfg,
            })
        result[tool_name] = compiled_preds

    return result


def _compile_capability_matrix(raw: dict[str, Any]) -> dict[str, frozenset[str]]:
    caps_raw = raw.get("capabilities", {})
    if not isinstance(caps_raw, dict):
        raise ManifestCompileError("Manifest 'capabilities' section must be a mapping")

    result: dict[str, frozenset[str]] = {}
    for trust_level, cap_list in caps_raw.items():
        if not isinstance(cap_list, list):
            raise ManifestCompileError(
                f"Capabilities for trust_level '{trust_level}' must be a list"
            )
        result[trust_level] = frozenset(cap_list)

    return result


def _compile_taint_rules(raw: dict[str, Any]) -> dict[tuple[str, str], str]:
    rules_raw = raw.get("taint_rules", [])
    if not isinstance(rules_raw, list):
        return {}

    result: dict[tuple[str, str], str] = {}
    for i, rule in enumerate(rules_raw):
        if not isinstance(rule, dict):
            raise ManifestCompileError(f"Taint rule {i} must be a mapping")
        source_taint = rule.get("source_taint", "")
        operation = rule.get("operation", "")
        res = rule.get("result", "")
        if not source_taint or not operation or not res:
            raise ManifestCompileError(
                f"Taint rule {i} must have source_taint, operation, result"
            )
        if res not in ("clear", "preserve"):
            raise ManifestCompileError(
                f"Taint rule {i}: result must be 'clear' or 'preserve', got '{res}'"
            )
        key = (source_taint, operation)
        if key in result:
            raise ManifestCompileError(
                f"Duplicate taint rule for ({source_taint}, {operation})"
            )
        result[key] = res

    return result


def _compile_escalation_rules(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules_raw = raw.get("escalation_rules", {})
    if not isinstance(rules_raw, dict):
        return {}
    return dict(rules_raw)
