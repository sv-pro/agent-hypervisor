"""
loader.py — Load and validate a World Manifest YAML file.

Validates that required top-level sections are present and that key fields
have acceptable values. Does not implement full JSON Schema validation —
that is deferred to the full schema validator (M2 follow-on).
"""

from __future__ import annotations

import yaml
from pathlib import Path

REQUIRED_SECTIONS = ["manifest", "actions", "trust_channels", "capability_matrix"]

VALID_TRUST_LEVELS = {"TRUSTED", "SEMI_TRUSTED", "UNTRUSTED"}
VALID_DECISIONS = {"require_approval", "deny", "simulate", "allow"}
VALID_SIDE_EFFECTS = {"internal_read", "internal_write", "external_read", "external_write"}


class ManifestValidationError(ValueError):
    pass


def load(path: str | Path) -> dict:
    """
    Load and validate a World Manifest YAML file.

    Returns the parsed manifest dict if valid.
    Raises ManifestValidationError with a descriptive message if invalid.
    """
    path = Path(path)
    if not path.exists():
        raise ManifestValidationError(f"Manifest file not found: {path}")

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ManifestValidationError("Manifest must be a YAML mapping at the top level.")

    # Required sections
    for section in REQUIRED_SECTIONS:
        if section not in raw:
            raise ManifestValidationError(
                f"Manifest is missing required section: '{section}'"
            )

    # manifest.name and manifest.version
    meta = raw["manifest"]
    for field in ("name", "version"):
        if not meta.get(field):
            raise ManifestValidationError(
                f"manifest.{field} is required and must be non-empty."
            )

    # actions: each must have name, reversible, side_effects
    for i, action in enumerate(raw.get("actions", [])):
        _validate_action(action, i)

    # trust_channels: each must have name and trust_level
    for i, channel in enumerate(raw.get("trust_channels", [])):
        _validate_channel(channel, i)

    # capability_matrix keys must be valid trust levels
    for level in raw.get("capability_matrix", {}):
        if level not in VALID_TRUST_LEVELS:
            raise ManifestValidationError(
                f"capability_matrix key '{level}' is not a valid trust level. "
                f"Valid values: {sorted(VALID_TRUST_LEVELS)}"
            )

    # escalation_conditions
    for i, cond in enumerate(raw.get("escalation_conditions", [])):
        _validate_escalation(cond, i)

    return raw


def _validate_action(action: dict, index: int) -> None:
    for field in ("name", "reversible", "side_effects"):
        if field not in action:
            raise ManifestValidationError(
                f"actions[{index}] is missing required field '{field}'."
            )
    for se in action.get("side_effects", []):
        if se not in VALID_SIDE_EFFECTS:
            raise ManifestValidationError(
                f"actions[{index}].side_effects contains unknown value '{se}'. "
                f"Valid values: {sorted(VALID_SIDE_EFFECTS)}"
            )
    output_trust = action.get("output_trust")
    if output_trust and output_trust not in VALID_TRUST_LEVELS:
        raise ManifestValidationError(
            f"actions[{index}].output_trust '{output_trust}' is not a valid trust level."
        )


def _validate_channel(channel: dict, index: int) -> None:
    for field in ("name", "trust_level", "taint_by_default"):
        if field not in channel:
            raise ManifestValidationError(
                f"trust_channels[{index}] is missing required field '{field}'."
            )
    if channel["trust_level"] not in VALID_TRUST_LEVELS:
        raise ManifestValidationError(
            f"trust_channels[{index}].trust_level '{channel['trust_level']}' is invalid. "
            f"Valid values: {sorted(VALID_TRUST_LEVELS)}"
        )


def _validate_escalation(cond: dict, index: int) -> None:
    for field in ("id", "trigger", "decision"):
        if field not in cond:
            raise ManifestValidationError(
                f"escalation_conditions[{index}] is missing required field '{field}'."
            )
    if cond["decision"] not in VALID_DECISIONS:
        raise ManifestValidationError(
            f"escalation_conditions[{index}].decision '{cond['decision']}' is invalid. "
            f"Valid values: {sorted(VALID_DECISIONS)}"
        )
