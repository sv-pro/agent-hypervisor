"""
validator.py — Schema-level validation for World Manifests (v0.3-T1).

Validates a World Manifest YAML file for:
  - Required fields and type correctness
  - Cross-references (entity → data_class, action → side_effect_surface, etc.)
  - Unknown action detection
  - Budget sanity: declared budgets must cover at least one model in the pricing registry

Designed to run before compilation (``ahc validate``) to surface authoring errors
early, before the manifest is compiled into a deployed policy.

Usage::

    result = validate(Path("manifests/workspace_v2.yaml"))
    if result.ok:
        print("✓ manifest valid")
    else:
        for err in result.errors:
            print(f"  ✗ {err}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ValidationResult:
    """
    The outcome of a validate() call.

    Attributes:
        ok:       True iff no errors were found.
        errors:   List of human-readable error messages (empty when ok).
        warnings: Non-fatal issues that do not block compilation.
    """
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def validate(path: str | Path) -> ValidationResult:
    """
    Validate a World Manifest YAML file.

    Supports both v1 and v2 manifests. v2 manifests receive additional
    cross-reference and budget sanity checks.

    Args:
        path: Path to the manifest YAML file.

    Returns:
        ValidationResult with errors and warnings populated.
        Never raises — all problems are captured in the result.
    """
    result = ValidationResult()
    path = Path(path)

    if not path.exists():
        result.error(f"File not found: {path}")
        return result

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        result.error(f"YAML parse error: {exc}")
        return result

    if not isinstance(raw, dict):
        result.error("Manifest must be a YAML mapping at the top level.")
        return result

    version = raw.get("version")

    if version == "2.0":
        _validate_v2(raw, result)
    else:
        _validate_v1(raw, result)

    return result


# ---------------------------------------------------------------------------
# v2 validation
# ---------------------------------------------------------------------------

def _validate_v2(raw: dict, result: ValidationResult) -> None:
    _check_required(raw, result, ["actions", "trust_channels", "capability_matrix"])

    actions = raw.get("actions") or {}
    if not isinstance(actions, dict):
        result.error("'actions' must be a mapping.")
        actions = {}

    _validate_v2_actions(actions, result)
    _validate_v2_trust_channels(raw.get("trust_channels") or {}, result)
    _validate_v2_capability_matrix(raw.get("capability_matrix") or {}, result)
    _validate_v2_entities(raw.get("entities") or {}, raw, result)
    _validate_v2_actors(raw.get("actors") or {}, result)
    _validate_v2_data_classes(raw.get("data_classes") or {}, result)
    _validate_v2_trust_zones(raw.get("trust_zones") or {}, raw, result)
    _validate_v2_side_effect_surfaces(raw.get("side_effect_surfaces") or {}, actions, result)
    _validate_v2_transition_policies(raw.get("transition_policies") or {}, raw, result)
    _validate_v2_budgets(raw.get("budgets") or {}, raw.get("economic") or {}, result)


def _validate_v2_actions(actions: dict, result: ValidationResult) -> None:
    valid_side_effects = {
        "internal_read", "internal_write", "external_read", "external_write"
    }
    for name, meta in actions.items():
        if not isinstance(meta, dict):
            result.error(f"actions.{name}: must be a mapping.")
            continue
        if "reversible" not in meta:
            result.error(f"actions.{name}: missing required field 'reversible'.")
        elif not isinstance(meta["reversible"], bool):
            result.error(f"actions.{name}.reversible: must be a boolean.")
        if "side_effects" not in meta:
            result.error(f"actions.{name}: missing required field 'side_effects'.")
        elif not isinstance(meta["side_effects"], list):
            result.error(f"actions.{name}.side_effects: must be a list.")
        else:
            for se in meta["side_effects"]:
                if se not in valid_side_effects:
                    result.error(
                        f"actions.{name}.side_effects: unknown value {se!r}. "
                        f"Valid: {sorted(valid_side_effects)}"
                    )


def _validate_v2_trust_channels(channels: dict, result: ValidationResult) -> None:
    valid_trust = {"TRUSTED", "SEMI_TRUSTED", "UNTRUSTED"}
    for name, cfg in channels.items():
        if not isinstance(cfg, dict):
            result.error(f"trust_channels.{name}: must be a mapping.")
            continue
        tl = cfg.get("trust_level")
        if tl is None:
            result.error(f"trust_channels.{name}: missing required field 'trust_level'.")
        elif tl not in valid_trust:
            result.error(
                f"trust_channels.{name}.trust_level: unknown value {tl!r}. "
                f"Valid: {sorted(valid_trust)}"
            )
        if "taint_by_default" not in cfg:
            result.error(f"trust_channels.{name}: missing required field 'taint_by_default'.")
        elif not isinstance(cfg["taint_by_default"], bool):
            result.error(f"trust_channels.{name}.taint_by_default: must be a boolean.")


def _validate_v2_capability_matrix(matrix: dict, result: ValidationResult) -> None:
    valid_trust = {"TRUSTED", "SEMI_TRUSTED", "UNTRUSTED"}
    for trust_level, caps in matrix.items():
        if trust_level not in valid_trust:
            result.error(
                f"capability_matrix: unknown trust tier {trust_level!r}. "
                f"Valid: {sorted(valid_trust)}"
            )
        if not isinstance(caps, list):
            result.error(f"capability_matrix.{trust_level}: must be a list of capability strings.")


def _validate_v2_entities(entities: dict, raw: dict, result: ValidationResult) -> None:
    declared_data_classes = set((raw.get("data_classes") or {}).keys())
    for name, cfg in entities.items():
        if not isinstance(cfg, dict):
            result.error(f"entities.{name}: must be a mapping.")
            continue
        if "type" not in cfg:
            result.error(f"entities.{name}: missing required field 'type'.")
        if "data_class" not in cfg:
            result.error(f"entities.{name}: missing required field 'data_class'.")
        elif declared_data_classes and cfg["data_class"] not in declared_data_classes:
            result.error(
                f"entities.{name}.data_class: references undeclared data class "
                f"{cfg['data_class']!r}. Declared: {sorted(declared_data_classes)}"
            )


def _validate_v2_actors(actors: dict, result: ValidationResult) -> None:
    valid_types = {"agent", "sub_agent", "service", "human"}
    for name, cfg in actors.items():
        if not isinstance(cfg, dict):
            result.error(f"actors.{name}: must be a mapping.")
            continue
        if "type" not in cfg:
            result.error(f"actors.{name}: missing required field 'type'.")
        elif cfg["type"] not in valid_types:
            result.error(
                f"actors.{name}.type: unknown value {cfg['type']!r}. "
                f"Valid: {sorted(valid_types)}"
            )
        if "trust_tier" not in cfg:
            result.error(f"actors.{name}: missing required field 'trust_tier'.")


def _validate_v2_data_classes(data_classes: dict, result: ValidationResult) -> None:
    for name, cfg in data_classes.items():
        if not isinstance(cfg, dict):
            result.error(f"data_classes.{name}: must be a mapping.")
            continue
        if "taint_label" not in cfg:
            result.error(f"data_classes.{name}: missing required field 'taint_label'.")
        if "confirmation" not in cfg:
            result.error(f"data_classes.{name}: missing required field 'confirmation'.")


def _validate_v2_trust_zones(trust_zones: dict, raw: dict, result: ValidationResult) -> None:
    declared_entities = set((raw.get("entities") or {}).keys())
    for name, cfg in trust_zones.items():
        if not isinstance(cfg, dict):
            result.error(f"trust_zones.{name}: must be a mapping.")
            continue
        if "default_trust" not in cfg:
            result.error(f"trust_zones.{name}: missing required field 'default_trust'.")
        for entity_ref in cfg.get("entities") or []:
            if declared_entities and entity_ref not in declared_entities:
                result.error(
                    f"trust_zones.{name}.entities: references undeclared entity "
                    f"{entity_ref!r}. Declared: {sorted(declared_entities)}"
                )


def _validate_v2_side_effect_surfaces(
    surfaces: dict | list, actions: dict, result: ValidationResult
) -> None:
    for label, cfg in _as_items(surfaces, "side_effect_surfaces"):
        if not isinstance(cfg, dict):
            result.error(f"{label}: must be a mapping.")
            continue
        action_ref = cfg.get("action")
        if action_ref is None:
            result.error(f"{label}: missing required field 'action'.")
        elif actions and action_ref not in actions:
            result.error(
                f"{label}.action: references undeclared action "
                f"{action_ref!r}. Declared: {sorted(actions.keys())}"
            )


def _validate_v2_transition_policies(policies: dict | list, raw: dict, result: ValidationResult) -> None:
    declared_zones = set((raw.get("trust_zones") or {}).keys())
    items = _as_items(policies, "transition_policies")
    for label, cfg in items:
        if not isinstance(cfg, dict):
            result.error(f"{label}: must be a mapping.")
            continue
        for zone_field in ("from_zone", "to_zone"):
            zone_ref = cfg.get(zone_field)
            if zone_ref and declared_zones and zone_ref not in declared_zones:
                result.error(
                    f"{label}.{zone_field}: references undeclared "
                    f"trust zone {zone_ref!r}. Declared: {sorted(declared_zones)}"
                )


def _validate_v2_budgets(budgets: dict, economic: dict, result: ValidationResult) -> None:
    """Budget sanity: if budgets declared, at least one model must have pricing."""
    if not budgets and not economic:
        return

    # Check that declared per_request / per_session are positive numbers.
    for key in ("per_request", "per_session"):
        val = budgets.get(key)
        if val is not None:
            try:
                f = float(val)
                if f <= 0:
                    result.error(f"budgets.{key}: must be a positive number, got {val!r}.")
            except (TypeError, ValueError):
                result.error(f"budgets.{key}: must be a number, got {val!r}.")

    # Budget sanity: if per_request or per_session is declared, the economic
    # section must contain at least one model with pricing so that the
    # EconomicPolicyEngine can produce replan hints.
    has_budget_limit = budgets.get("per_request") or budgets.get("per_session")
    if has_budget_limit:
        model_pricing = economic.get("model_pricing") or {}
        if not model_pricing:
            result.warn(
                "budgets declares per_request/per_session limits but "
                "economic.model_pricing is empty. The EconomicPolicyEngine "
                "will always produce deny verdicts (unknown model cost = ∞). "
                "Add at least one model entry to economic.model_pricing."
            )


# ---------------------------------------------------------------------------
# v1 validation
# ---------------------------------------------------------------------------

def _validate_v1(raw: dict, result: ValidationResult) -> None:
    _check_required(raw, result, ["manifest", "actions", "capabilities"])

    manifest_meta = raw.get("manifest")
    if isinstance(manifest_meta, dict):
        if "name" not in manifest_meta:
            result.error("manifest.name: required field missing.")
    elif manifest_meta is not None:
        result.error("'manifest' must be a mapping.")

    actions = raw.get("actions")
    if isinstance(actions, list):
        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                result.error(f"actions[{i}]: must be a mapping.")
                continue
            if "name" not in action:
                result.error(f"actions[{i}]: missing required field 'name'.")
            if "type" not in action:
                result.error(f"actions[{i}]: missing required field 'type'.")
    elif actions is not None:
        result.error("'actions' must be a list for v1 manifests.")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _check_required(raw: dict, result: ValidationResult, fields: list[str]) -> None:
    for field_name in fields:
        if field_name not in raw:
            result.error(f"Missing required top-level field: '{field_name}'.")


def _as_items(collection: dict | list, section: str) -> list[tuple[str, Any]]:
    """Normalise a dict or list section into (label, cfg) pairs."""
    if isinstance(collection, dict):
        return [(f"{section}.{k}", v) for k, v in collection.items()]
    if isinstance(collection, list):
        return [(f"{section}[{i}]", v) for i, v in enumerate(collection)]
    return []
