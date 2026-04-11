"""loader_v2.py — Load and validate a World Manifest v2.0 YAML file.

Validation rules:
  - version field must be exactly "2.0"
  - Required sections: manifest (with name), actions, trust_channels, capability_matrix
  - trust_channels: each entry must have trust_level (TRUSTED/SEMI_TRUSTED/UNTRUSTED)
                    and taint_by_default (bool)
  - capability_matrix: keys must be valid trust tiers
  - actions: each must have reversible (bool) and side_effects (list)
  - entities: each entry must have type and data_class
  - actors: each entry must have type and trust_tier
  - data_classes: each entry must have taint_label and confirmation
  - trust_zones: each entry must have default_trust
  - confirmation_classes: each entry must have description and blocking (bool)
  - Cross-validation: entity.data_class must reference a declared data_class;
    trust_zone.entities must reference declared entities;
    side_effect_surface.action must reference a declared action;
    transition_policy zones must reference declared trust_zones

v1 manifests (missing version: "2.0" or using the v1 section structure) are
rejected with a clear error message pointing to `ahc migrate`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schema_v2 import (
    Actor,
    ConfirmationClass,
    DataClass,
    Entity,
    ObservabilityDefaults,
    ObservabilitySpec,
    SideEffectSurface,
    TransitionPolicy,
    TrustZone,
    WorldManifestV2,
)

VALID_TRUST_TIERS = {"TRUSTED", "SEMI_TRUSTED", "UNTRUSTED"}
VALID_SIDE_EFFECTS = {"internal_read", "internal_write", "external_read", "external_write"}
VALID_ACTOR_TYPES = {"agent", "sub_agent", "service", "human"}


class ManifestV2ValidationError(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    """Load and validate a v2 World Manifest YAML file.

    Returns the parsed manifest dict if valid.
    Raises ManifestV2ValidationError with a descriptive message if invalid.

    v1 manifests (missing version: "2.0") are rejected with a migration hint.
    """
    path = Path(path)
    if not path.exists():
        raise ManifestV2ValidationError(f"Manifest file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ManifestV2ValidationError("Manifest must be a YAML mapping at the top level.")

    _check_version(raw, path)
    _validate_manifest_meta(raw)
    _validate_trust_channels(raw)
    _validate_capability_matrix(raw)
    _validate_actions(raw)
    _validate_entities(raw)
    _validate_actors(raw)
    _validate_data_classes(raw)
    _validate_trust_zones(raw)
    _validate_confirmation_classes(raw)
    _validate_side_effect_surfaces(raw)
    _validate_transition_policies(raw)
    _cross_validate(raw)

    return raw


def load_typed(path: str | Path) -> WorldManifestV2:
    """Load and validate a v2 manifest, returning a typed WorldManifestV2.

    Equivalent to load() but parses the raw dict into Python dataclasses.
    """
    raw = load(path)
    return _parse_manifest(raw)


# ── Internal validators ───────────────────────────────────────────────────────


def _check_version(raw: dict, path: Path) -> None:
    version = raw.get("version")
    if version is None:
        raise ManifestV2ValidationError(
            f"{path}: missing 'version' field.\n"
            "This looks like a v1 manifest. Run 'ahc migrate' to convert it:\n"
            f"  ahc migrate {path} --output {path.stem}_v2.yaml"
        )
    if str(version) != "2.0":
        raise ManifestV2ValidationError(
            f"{path}: version '{version}' is not supported by the v2 compiler.\n"
            "Expected: version: \"2.0\"\n"
            "If this is a v1 manifest, run 'ahc migrate' to convert it:\n"
            f"  ahc migrate {path} --output {path.stem}_v2.yaml"
        )


def _validate_manifest_meta(raw: dict) -> None:
    meta = raw.get("manifest")
    if not meta:
        raise ManifestV2ValidationError(
            "Missing required section 'manifest'. "
            "Add a 'manifest:' block with at least a 'name' field."
        )
    if not isinstance(meta, dict):
        raise ManifestV2ValidationError("'manifest' must be a mapping.")
    if not meta.get("name"):
        raise ManifestV2ValidationError("manifest.name is required and must be non-empty.")


def _validate_trust_channels(raw: dict) -> None:
    channels = raw.get("trust_channels")
    if channels is None:
        raise ManifestV2ValidationError("Missing required section 'trust_channels'.")
    if not isinstance(channels, dict):
        raise ManifestV2ValidationError("'trust_channels' must be a mapping.")
    for name, spec in channels.items():
        if not isinstance(spec, dict):
            raise ManifestV2ValidationError(
                f"trust_channels.{name} must be a mapping."
            )
        level = spec.get("trust_level")
        if level not in VALID_TRUST_TIERS:
            raise ManifestV2ValidationError(
                f"trust_channels.{name}.trust_level '{level}' is invalid. "
                f"Valid values: {sorted(VALID_TRUST_TIERS)}"
            )
        if "taint_by_default" not in spec:
            raise ManifestV2ValidationError(
                f"trust_channels.{name} is missing required field 'taint_by_default'."
            )
        if not isinstance(spec["taint_by_default"], bool):
            raise ManifestV2ValidationError(
                f"trust_channels.{name}.taint_by_default must be a boolean."
            )


def _validate_capability_matrix(raw: dict) -> None:
    matrix = raw.get("capability_matrix")
    if matrix is None:
        raise ManifestV2ValidationError("Missing required section 'capability_matrix'.")
    if not isinstance(matrix, dict):
        raise ManifestV2ValidationError("'capability_matrix' must be a mapping.")
    for tier in matrix:
        if tier not in VALID_TRUST_TIERS:
            raise ManifestV2ValidationError(
                f"capability_matrix key '{tier}' is not a valid trust tier. "
                f"Valid values: {sorted(VALID_TRUST_TIERS)}"
            )


def _validate_actions(raw: dict) -> None:
    actions = raw.get("actions")
    if actions is None:
        raise ManifestV2ValidationError("Missing required section 'actions'.")
    if not isinstance(actions, dict):
        raise ManifestV2ValidationError("'actions' must be a mapping.")
    for name, spec in actions.items():
        if not isinstance(spec, dict):
            raise ManifestV2ValidationError(f"actions.{name} must be a mapping.")
        if "reversible" not in spec:
            raise ManifestV2ValidationError(
                f"actions.{name} is missing required field 'reversible'."
            )
        if not isinstance(spec["reversible"], bool):
            raise ManifestV2ValidationError(
                f"actions.{name}.reversible must be a boolean."
            )
        if "side_effects" not in spec:
            raise ManifestV2ValidationError(
                f"actions.{name} is missing required field 'side_effects'."
            )
        for se in spec.get("side_effects", []):
            if se not in VALID_SIDE_EFFECTS:
                raise ManifestV2ValidationError(
                    f"actions.{name}.side_effects contains unknown value '{se}'. "
                    f"Valid values: {sorted(VALID_SIDE_EFFECTS)}"
                )


def _validate_entities(raw: dict) -> None:
    entities = raw.get("entities", {})
    if not isinstance(entities, dict):
        raise ManifestV2ValidationError("'entities' must be a mapping.")
    for name, spec in entities.items():
        if not isinstance(spec, dict):
            raise ManifestV2ValidationError(f"entities.{name} must be a mapping.")
        for field in ("type", "data_class"):
            if not spec.get(field):
                raise ManifestV2ValidationError(
                    f"entities.{name} is missing required field '{field}'."
                )


def _validate_actors(raw: dict) -> None:
    actors = raw.get("actors", {})
    if not isinstance(actors, dict):
        raise ManifestV2ValidationError("'actors' must be a mapping.")
    for name, spec in actors.items():
        if not isinstance(spec, dict):
            raise ManifestV2ValidationError(f"actors.{name} must be a mapping.")
        actor_type = spec.get("type")
        if actor_type not in VALID_ACTOR_TYPES:
            raise ManifestV2ValidationError(
                f"actors.{name}.type '{actor_type}' is invalid. "
                f"Valid values: {sorted(VALID_ACTOR_TYPES)}"
            )
        trust_tier = spec.get("trust_tier")
        if trust_tier not in VALID_TRUST_TIERS:
            raise ManifestV2ValidationError(
                f"actors.{name}.trust_tier '{trust_tier}' is invalid. "
                f"Valid values: {sorted(VALID_TRUST_TIERS)}"
            )


def _validate_data_classes(raw: dict) -> None:
    data_classes = raw.get("data_classes", {})
    if not isinstance(data_classes, dict):
        raise ManifestV2ValidationError("'data_classes' must be a mapping.")
    for name, spec in data_classes.items():
        if not isinstance(spec, dict):
            raise ManifestV2ValidationError(f"data_classes.{name} must be a mapping.")
        for field in ("taint_label", "confirmation"):
            if not spec.get(field):
                raise ManifestV2ValidationError(
                    f"data_classes.{name} is missing required field '{field}'."
                )


def _validate_trust_zones(raw: dict) -> None:
    zones = raw.get("trust_zones", {})
    if not isinstance(zones, dict):
        raise ManifestV2ValidationError("'trust_zones' must be a mapping.")
    for name, spec in zones.items():
        if not isinstance(spec, dict):
            raise ManifestV2ValidationError(f"trust_zones.{name} must be a mapping.")
        trust = spec.get("default_trust")
        if trust not in VALID_TRUST_TIERS:
            raise ManifestV2ValidationError(
                f"trust_zones.{name}.default_trust '{trust}' is invalid. "
                f"Valid values: {sorted(VALID_TRUST_TIERS)}"
            )


def _validate_confirmation_classes(raw: dict) -> None:
    classes = raw.get("confirmation_classes", {})
    if not isinstance(classes, dict):
        raise ManifestV2ValidationError("'confirmation_classes' must be a mapping.")
    for name, spec in classes.items():
        if not isinstance(spec, dict):
            raise ManifestV2ValidationError(f"confirmation_classes.{name} must be a mapping.")
        if "description" not in spec:
            raise ManifestV2ValidationError(
                f"confirmation_classes.{name} is missing required field 'description'."
            )
        if "blocking" not in spec:
            raise ManifestV2ValidationError(
                f"confirmation_classes.{name} is missing required field 'blocking'."
            )
        if not isinstance(spec["blocking"], bool):
            raise ManifestV2ValidationError(
                f"confirmation_classes.{name}.blocking must be a boolean."
            )


def _validate_side_effect_surfaces(raw: dict) -> None:
    surfaces = raw.get("side_effect_surfaces", [])
    if not isinstance(surfaces, list):
        raise ManifestV2ValidationError("'side_effect_surfaces' must be a list.")
    for i, entry in enumerate(surfaces):
        if not isinstance(entry, dict):
            raise ManifestV2ValidationError(f"side_effect_surfaces[{i}] must be a mapping.")
        if not entry.get("action"):
            raise ManifestV2ValidationError(
                f"side_effect_surfaces[{i}] is missing required field 'action'."
            )


def _validate_transition_policies(raw: dict) -> None:
    policies = raw.get("transition_policies", [])
    if not isinstance(policies, list):
        raise ManifestV2ValidationError("'transition_policies' must be a list.")
    for i, entry in enumerate(policies):
        if not isinstance(entry, dict):
            raise ManifestV2ValidationError(f"transition_policies[{i}] must be a mapping.")
        for field in ("from_zone", "to_zone", "allowed"):
            if field not in entry:
                raise ManifestV2ValidationError(
                    f"transition_policies[{i}] is missing required field '{field}'."
                )
        if not isinstance(entry["allowed"], bool):
            raise ManifestV2ValidationError(
                f"transition_policies[{i}].allowed must be a boolean."
            )


def _cross_validate(raw: dict) -> None:
    """Cross-validate references between sections."""
    declared_data_classes = set(raw.get("data_classes", {}).keys())
    declared_entities = set(raw.get("entities", {}).keys())
    declared_actions = set(raw.get("actions", {}).keys())
    declared_trust_zones = set(raw.get("trust_zones", {}).keys())
    declared_confirmation_classes = set(raw.get("confirmation_classes", {}).keys())

    # entity.data_class must reference a declared data_class
    if declared_data_classes:
        for name, spec in raw.get("entities", {}).items():
            dc = spec.get("data_class")
            if dc and dc not in declared_data_classes:
                raise ManifestV2ValidationError(
                    f"entities.{name}.data_class '{dc}' is not declared in data_classes. "
                    f"Declared: {sorted(declared_data_classes)}"
                )

    # trust_zone.entities must reference declared entities
    if declared_entities:
        for name, spec in raw.get("trust_zones", {}).items():
            for entity_ref in spec.get("entities", []):
                if entity_ref not in declared_entities:
                    raise ManifestV2ValidationError(
                        f"trust_zones.{name}.entities references unknown entity '{entity_ref}'. "
                        f"Declared entities: {sorted(declared_entities)}"
                    )

    # side_effect_surface.action must reference a declared action
    for i, surface in enumerate(raw.get("side_effect_surfaces", [])):
        action_ref = surface.get("action")
        if action_ref and action_ref not in declared_actions:
            raise ManifestV2ValidationError(
                f"side_effect_surfaces[{i}].action '{action_ref}' is not declared in actions. "
                f"Declared actions: {sorted(declared_actions)}"
            )

    # transition_policy zones must reference declared trust_zones
    if declared_trust_zones:
        for i, policy in enumerate(raw.get("transition_policies", [])):
            for field in ("from_zone", "to_zone"):
                zone_ref = policy.get(field)
                if zone_ref and zone_ref not in declared_trust_zones:
                    raise ManifestV2ValidationError(
                        f"transition_policies[{i}].{field} '{zone_ref}' is not declared "
                        f"in trust_zones. Declared: {sorted(declared_trust_zones)}"
                    )

    # action.confirmation_class (if present) must reference a declared confirmation_class
    if declared_confirmation_classes:
        for name, spec in raw.get("actions", {}).items():
            cc = spec.get("confirmation_class")
            if cc and cc not in declared_confirmation_classes:
                raise ManifestV2ValidationError(
                    f"actions.{name}.confirmation_class '{cc}' is not declared in "
                    f"confirmation_classes. Declared: {sorted(declared_confirmation_classes)}"
                )


# ── Dict → typed objects ──────────────────────────────────────────────────────


def _parse_manifest(raw: dict) -> WorldManifestV2:
    """Parse a validated raw dict into a typed WorldManifestV2."""
    meta = raw["manifest"]

    entities = {
        name: Entity(
            name=name,
            type=spec["type"],
            data_class=spec["data_class"],
            identity_fields=tuple(spec.get("identity_fields", [])),
            description=spec.get("description", ""),
        )
        for name, spec in raw.get("entities", {}).items()
    }

    actors = {
        name: Actor(
            name=name,
            type=spec["type"],
            trust_tier=spec["trust_tier"],
            permission_scope=tuple(spec.get("permission_scope", [])),
            description=spec.get("description", ""),
        )
        for name, spec in raw.get("actors", {}).items()
    }

    data_classes = {
        name: DataClass(
            name=name,
            description=spec.get("description", ""),
            taint_label=spec["taint_label"],
            confirmation=spec["confirmation"],
            retention=spec.get("retention", "session"),
        )
        for name, spec in raw.get("data_classes", {}).items()
    }

    trust_zones = {
        name: TrustZone(
            name=name,
            description=spec.get("description", ""),
            default_trust=spec["default_trust"],
            entities=tuple(spec.get("entities", [])),
        )
        for name, spec in raw.get("trust_zones", {}).items()
    }

    confirmation_classes = {
        name: ConfirmationClass(
            name=name,
            description=spec["description"],
            blocking=spec["blocking"],
        )
        for name, spec in raw.get("confirmation_classes", {}).items()
    }

    side_effect_surfaces = tuple(
        SideEffectSurface(
            action=s["action"],
            touches=tuple(s.get("touches", [])),
            data_classes_affected=tuple(s.get("data_classes_affected", [])),
            description=s.get("description", ""),
        )
        for s in raw.get("side_effect_surfaces", [])
    )

    transition_policies = tuple(
        TransitionPolicy(
            from_zone=p["from_zone"],
            to_zone=p["to_zone"],
            allowed=p["allowed"],
            confirmation=p.get("confirmation", "auto"),
            description=p.get("description", ""),
        )
        for p in raw.get("transition_policies", [])
    )

    obs_raw = raw.get("observability", {})
    obs_defaults_raw = obs_raw.get("defaults", {})
    obs_defaults = ObservabilityDefaults(
        log_fields=tuple(obs_defaults_raw.get("log_fields", ["action", "timestamp", "actor", "decision"])),
        redact_fields=tuple(obs_defaults_raw.get("redact_fields", [])),
        retain_duration=obs_defaults_raw.get("retain_duration", "90d"),
    )
    per_action_obs = {
        action: ObservabilityDefaults(
            log_fields=tuple(spec.get("log_fields", [])),
            redact_fields=tuple(spec.get("redact_fields", [])),
            retain_duration=spec.get("retain_duration", obs_defaults.retain_duration),
        )
        for action, spec in obs_raw.get("per_action", {}).items()
    }
    observability = ObservabilitySpec(defaults=obs_defaults, per_action=per_action_obs)

    return WorldManifestV2(
        name=meta["name"],
        version=str(raw.get("version", "2.0")),
        description=meta.get("description", ""),
        entities=entities,
        actors=actors,
        data_classes=data_classes,
        trust_zones=trust_zones,
        confirmation_classes=confirmation_classes,
        side_effect_surfaces=side_effect_surfaces,
        transition_policies=transition_policies,
        observability=observability,
        actions=raw.get("actions", {}),
        trust_channels=raw.get("trust_channels", {}),
        capability_matrix=raw.get("capability_matrix", {}),
        defaults=raw.get("defaults", {}),
        trust_levels=tuple(raw.get("trust_levels", [])),
        taint_rules=tuple(raw.get("taint_rules", [])),
        escalation_rules=raw.get("escalation_rules", {}),
        schemas=raw.get("schemas", {}),
        predicates=raw.get("predicates", {}),
    )
