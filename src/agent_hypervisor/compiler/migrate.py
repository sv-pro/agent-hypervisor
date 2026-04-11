"""migrate.py — v1 → v2 World Manifest migration tool.

Converts a v1 manifest (loader.py format) to a v2 stub (loader_v2.py format).

Migration strategy:
  - Mechanical sections (actions, trust_channels, capability_matrix, taint_rules,
    escalation_conditions) are carried over with v2 field additions where they
    can be inferred from v1 fields.
  - New semantic sections (entities, actors, data_classes, trust_zones,
    confirmation_classes, side_effect_surfaces, transition_policies, observability)
    are generated as stubs with TODO markers for human review.
  - The output is a valid YAML file that passes the v2 loader — after the human
    fills in the TODO sections.

Usage:
    from compiler.migrate import migrate_v1_to_v2
    output_yaml = migrate_v1_to_v2(input_path)

    Or via CLI:
    ahc migrate manifest_v1.yaml --output manifest_v2.yaml
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import yaml

from .loader import ManifestValidationError
from .loader import load as load_v1


def migrate_v1_to_v2(source: str | Path, *, strict: bool = False) -> str:
    """Read a v1 manifest and return a v2 YAML string.

    Args:
        source: Path to the v1 manifest YAML.
        strict: If True, raise an error if the source already declares version: "2.0".

    Returns:
        A YAML string representing the migrated v2 manifest.
        TODO markers in comments indicate sections requiring human review.

    Raises:
        ManifestValidationError: if the source fails v1 validation.
        ValueError: if strict=True and source is already v2.
    """
    source = Path(source)
    raw = load_v1(source)

    if strict and str(raw.get("version", "")) == "2.0":
        raise ValueError(f"{source} is already a v2 manifest.")

    return _build_v2_yaml(raw, source_name=source.stem)


def _build_v2_yaml(v1: dict[str, Any], *, source_name: str) -> str:
    """Build the v2 YAML string from a validated v1 dict."""
    lines: list[str] = []

    _header(lines, source_name)
    _manifest_meta(lines, v1)
    _entities_stub(lines)
    _actors_stub(lines)
    _data_classes_stub(lines)
    _trust_zones_stub(lines)
    _confirmation_classes(lines)
    _side_effect_surfaces_stub(lines, v1)
    _transition_policies_stub(lines)
    _observability_stub(lines)
    _defaults(lines, v1)
    _trust_channels(lines, v1)
    _trust_levels(lines, v1)
    _capability_matrix(lines, v1)
    _actions(lines, v1)
    _taint_rules(lines, v1)
    _escalation_rules(lines, v1)

    return "\n".join(lines) + "\n"


# ── Section builders ──────────────────────────────────────────────────────────


def _header(lines: list[str], source_name: str) -> None:
    lines += [
        f"# Migrated from {source_name} (v1 → v2) by ahc migrate",
        "# Review all sections marked TODO before using this manifest.",
        "#",
        "# Sections carried over mechanically: actions, trust_channels,",
        "#   capability_matrix, taint_rules, escalation_conditions.",
        "# Sections requiring human review: entities, actors, data_classes,",
        "#   trust_zones, side_effect_surfaces, transition_policies, observability.",
        "",
        'version: "2.0"',
        "",
    ]


def _manifest_meta(lines: list[str], v1: dict) -> None:
    meta = v1.get("manifest", {})
    name = meta.get("name", "migrated-manifest")
    description = meta.get("description", "Migrated from v1 manifest.")
    lines += [
        "manifest:",
        f"  name: {name}",
        f"  description: {description}",
        "",
    ]


def _entities_stub(lines: list[str]) -> None:
    lines += [
        "# TODO: Define named objects in the agent's world.",
        "# Each entity needs: type, data_class (from data_classes section), description.",
        "# Examples: user_inbox, shared_drive, external_contact.",
        "entities:",
        "  # example_entity:",
        "  #   type: document               # user | account | document | queue | mailbox | contact | other",
        "  #   data_class: internal         # references a data_classes entry",
        "  #   description: Human-readable note",
        "  #   identity_fields: [id]        # fields that uniquely identify instances",
        "",
    ]


def _actors_stub(lines: list[str]) -> None:
    lines += [
        "# TODO: Define execution participants.",
        "# Each actor needs: type, trust_tier, permission_scope, description.",
        "actors:",
        "  # primary_agent:",
        "  #   type: agent                  # agent | sub_agent | service | human",
        "  #   trust_tier: TRUSTED          # TRUSTED | SEMI_TRUSTED | UNTRUSTED",
        "  #   permission_scope:",
        "  #     - read_only",
        "  #     - internal_write",
        "  #   description: The primary executing agent",
        "",
    ]


def _data_classes_stub(lines: list[str]) -> None:
    lines += [
        "# TODO: Define data classifications for your deployment.",
        "# Recommended: start with public, internal, pii, credentials.",
        "# Each class needs: taint_label, confirmation (from confirmation_classes).",
        "data_classes:",
        "  public:",
        "    description: Publicly available data — no handling restrictions",
        "    taint_label: clean",
        "    confirmation: auto",
        "    retention: session",
        "  internal:",
        "    description: Internal data — must not leave the system boundary without review",
        "    taint_label: internal",
        "    confirmation: soft_confirm",
        "    retention: 90d",
        "  pii:",
        "    description: Personally identifiable information",
        "    taint_label: pii",
        "    confirmation: hard_confirm",
        "    retention: 365d",
        "  credentials:",
        "    description: Authentication tokens, passwords, API keys",
        "    taint_label: credentials",
        "    confirmation: require_human",
        "    retention: never",
        "",
    ]


def _trust_zones_stub(lines: list[str]) -> None:
    lines += [
        "# TODO: Define trust zones for your deployment.",
        "# Each zone needs: description, default_trust, entities list.",
        "trust_zones:",
        "  # internal_workspace:",
        "  #   description: The agent's trusted execution environment",
        "  #   default_trust: TRUSTED",
        "  #   entities: []           # list entity names defined above",
        "  # external_network:",
        "  #   description: External internet and third-party services",
        "  #   default_trust: UNTRUSTED",
        "  #   entities: []",
        "",
    ]


def _confirmation_classes(lines: list[str]) -> None:
    lines += [
        "# Standard confirmation classes — customize or extend as needed.",
        "confirmation_classes:",
        "  auto:",
        "    description: No confirmation needed — execute immediately",
        "    blocking: false",
        "  soft_confirm:",
        "    description: Agent-level gate — dry-run, log, but do not block execution",
        "    blocking: false",
        "  hard_confirm:",
        "    description: Requires approval before execution",
        "    blocking: true",
        "  require_human:",
        "    description: Blocks execution until explicit human sign-off is received",
        "    blocking: true",
        "",
    ]


def _side_effect_surfaces_stub(lines: list[str], v1: dict) -> None:
    lines.append("# TODO: Declare what each action can touch (entities, zones, data_classes).")
    lines.append("# One entry per action that has external_boundary=true or irreversible=true.")
    lines.append("side_effect_surfaces:")

    # Emit stub entries for actions with external side effects
    for action in v1.get("actions", []):
        ses = action.get("side_effects", [])
        if any(se in ("external_write", "external_read") for se in ses):
            name = action["name"]
            lines += [
                f"  # - action: {name}",
                "  #   touches: []          # entity or zone names",
                "  #   data_classes_affected: []",
                "  #   description: TODO",
            ]

    if not any(
        se in ("external_write", "external_read")
        for a in v1.get("actions", [])
        for se in a.get("side_effects", [])
    ):
        lines.append("  []  # no external-boundary actions detected in v1 manifest")

    lines.append("")


def _transition_policies_stub(lines: list[str]) -> None:
    lines += [
        "# TODO: Define zone-crossing rules.",
        "# Recommended: deny internal → external by default.",
        "transition_policies:",
        "  # - from_zone: internal_workspace",
        "  #   to_zone: external_network",
        "  #   allowed: false",
        "  #   confirmation: require_human",
        "  #   description: Internal data must not reach external network",
        "",
    ]


def _observability_stub(lines: list[str]) -> None:
    lines += [
        "# TODO: Configure audit logging per action.",
        "observability:",
        "  defaults:",
        "    log_fields:",
        "      - action",
        "      - timestamp",
        "      - actor",
        "      - decision",
        "    redact_fields: []",
        "    retain_duration: 90d",
        "  per_action: {}  # add per-action overrides here",
        "",
    ]


def _defaults(lines: list[str], v1: dict) -> None:
    # v1 does not have a defaults section; emit standard fail-closed defaults
    lines += [
        "defaults:",
        "  unknown_action: deny",
        "  unknown_tool: deny",
        "  missing_capability: deny",
        "  schema_mismatch: deny",
        "  tainted_external: deny",
        "  unknown_transformation_taint: preserve",
        "",
    ]


def _trust_channels(lines: list[str], v1: dict) -> None:
    lines.append("trust_channels:")
    for channel in v1.get("trust_channels", []):
        name = channel["name"]
        level = channel["trust_level"]
        taint = str(channel.get("taint_by_default", True)).lower()
        desc = channel.get("description", "")
        lines += [
            f"  {name}:",
            f"    trust_level: {level}",
            f"    taint_by_default: {taint}",
        ]
        if desc:
            lines.append(f"    description: {desc}")
    lines.append("")


def _trust_levels(lines: list[str], v1: dict) -> None:
    # v1 trust levels from VALID_TRUST_LEVELS; emit standard ordering
    lines += [
        "trust_levels:",
        "  - UNTRUSTED",
        "  - SEMI_TRUSTED",
        "  - TRUSTED",
        "",
    ]


def _capability_matrix(lines: list[str], v1: dict) -> None:
    matrix = v1.get("capability_matrix", {})
    lines.append("capability_matrix:")
    for tier in ("UNTRUSTED", "SEMI_TRUSTED", "TRUSTED"):
        caps = matrix.get(tier, [])
        lines.append(f"  {tier}:")
        if caps:
            for cap in caps:
                lines.append(f"    - {cap}")
        else:
            lines.append("    []")
    lines.append("")


def _actions(lines: list[str], v1: dict) -> None:
    lines.append("actions:")
    for action in v1.get("actions", []):
        name = action["name"]
        reversible = str(action.get("reversible", True)).lower()
        side_effects = action.get("side_effects", [])
        output_trust = action.get("output_trust", "")

        # Infer v2 fields from v1
        has_external = any(se in ("external_write", "external_read") for se in side_effects)
        irreversible = not action.get("reversible", True)

        lines += [
            f"  {name}:",
            f"    reversible: {reversible}",
            "    side_effects:",
        ]
        for se in side_effects:
            lines.append(f"      - {se}")
        if not side_effects:
            lines.append("      []")

        # v2 additions — inferred where possible, TODO otherwise
        lines += [
            "    # v2 fields (review and complete):",
            "    action_class: TODO          # read_only | reversible_internal | irreversible_internal | external_boundary",
            "    risk_class: TODO            # low | medium | high | critical",
            "    required_capabilities: []  # TODO: list capabilities from capability_matrix",
            f"    requires_approval: {'true' if irreversible else 'false'}",
            f"    irreversible: {'true' if irreversible else 'false'}",
            f"    external_boundary: {'true' if has_external else 'false'}",
            "    taint_passthrough: true     # TODO: set false for aggregation-only actions",
            "    confirmation_class: auto    # TODO: set appropriate confirmation_class",
        ]
        if output_trust:
            lines.append(f"    # output_trust: {output_trust}  (v1 field — map to trust_channels if needed)")
        desc = action.get("description", "")
        if desc:
            lines.append(f"    description: {desc}")
    lines.append("")


def _taint_rules(lines: list[str], v1: dict) -> None:
    taint_rules = v1.get("taint_rules", [])
    if not taint_rules:
        return
    lines.append("taint_rules:")
    for rule in taint_rules:
        lines += [
            "  - source_taint: " + str(rule.get("source_taint", "tainted")),
            "    operation: " + str(rule.get("operation", "")),
            "    result: " + str(rule.get("result", "preserve")),
        ]
    lines.append("")


def _escalation_rules(lines: list[str], v1: dict) -> None:
    conditions = v1.get("escalation_conditions", [])
    if not conditions:
        return
    lines.append("escalation_rules:")
    for cond in conditions:
        rule_id = cond.get("id", "")
        trigger = cond.get("trigger", "")
        decision = cond.get("decision", "")
        # Map v1 escalation_conditions to v2 escalation_rules format
        # v1: {id, trigger, decision}  →  v2: {action_name: {condition, reason, rule_id}}
        lines += [
            f"  # Migrated from escalation_conditions.{rule_id}:",
            f"  # TODO: map trigger '{trigger}' to an action name",
            f"  # {rule_id}:",
            f"  #   condition: {trigger}",
            f"  #   reason: Migrated from v1 escalation — review and update",
            f"  #   rule_id: {rule_id}",
        ]
    lines.append("")
