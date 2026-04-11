"""differ.py — Structural diff between two World Manifest versions.

Computes a semantic diff between two manifest dicts, identifying:
  - Actions added, removed, or changed
  - Trust channels added, removed, or changed
  - Capability matrix changes
  - Taint rules added or removed
  - v2 world-model sections: entities, actors, data_classes, trust_zones,
    confirmation_classes, side_effect_surfaces, transition_policies

Usage:
    diff = diff_manifests(old_manifest_dict, new_manifest_dict)
    for change in diff.changes:
        print(change)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Change types ──────────────────────────────────────────────────────────────

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"


@dataclass(frozen=True)
class ManifestChange:
    """A single change between two manifest versions."""

    section: str   # e.g. "actions", "trust_channels", "capability_matrix"
    kind: str      # added | removed | changed
    key: str       # name of the changed element (action name, channel name, etc.)
    field: str     # specific field that changed, or "" for the whole element
    old_value: Any = None
    new_value: Any = None

    def __str__(self) -> str:
        if self.kind == ADDED:
            return f"[+] {self.section}.{self.key}: added"
        if self.kind == REMOVED:
            return f"[-] {self.section}.{self.key}: removed"
        if self.field:
            return (
                f"[~] {self.section}.{self.key}.{self.field}: "
                f"{self.old_value!r} → {self.new_value!r}"
            )
        return f"[~] {self.section}.{self.key}: changed"


@dataclass
class ManifestDiff:
    """Full structural diff between two manifest versions."""

    old_name: str
    new_name: str
    changes: list[ManifestChange] = field(default_factory=list)

    @property
    def added(self) -> list[ManifestChange]:
        return [c for c in self.changes if c.kind == ADDED]

    @property
    def removed(self) -> list[ManifestChange]:
        return [c for c in self.changes if c.kind == REMOVED]

    @property
    def changed(self) -> list[ManifestChange]:
        return [c for c in self.changes if c.kind == CHANGED]

    @property
    def is_empty(self) -> bool:
        return len(self.changes) == 0

    def changes_in_section(self, section: str) -> list[ManifestChange]:
        return [c for c in self.changes if c.section == section]

    def summary(self) -> str:
        parts = []
        if self.added:
            parts.append(f"{len(self.added)} added")
        if self.removed:
            parts.append(f"{len(self.removed)} removed")
        if self.changed:
            parts.append(f"{len(self.changed)} changed")
        if not parts:
            return "No changes"
        return ", ".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────


def diff_manifests(old: dict[str, Any], new: dict[str, Any]) -> ManifestDiff:
    """Compute a structural diff between two manifest dicts.

    Both manifests should be validated dicts (from loader_v2.load() or
    loader.load()). The diff is purely structural — it does not evaluate
    security implications of the changes.

    Returns a ManifestDiff listing all added, removed, and changed elements.
    """
    old_name = old.get("manifest", {}).get("name", old.get("workflow_id", "old"))
    new_name = new.get("manifest", {}).get("name", new.get("workflow_id", "new"))
    diff = ManifestDiff(old_name=old_name, new_name=new_name)

    _diff_actions(old, new, diff)
    _diff_trust_channels(old, new, diff)
    _diff_capability_matrix(old, new, diff)
    _diff_taint_rules(old, new, diff)
    _diff_escalation_rules(old, new, diff)

    # v2 world-model sections
    _diff_dict_section(old, new, diff, "entities", _ACTION_FIELDS)
    _diff_dict_section(old, new, diff, "actors", _ACTOR_FIELDS)
    _diff_dict_section(old, new, diff, "data_classes", _DC_FIELDS)
    _diff_dict_section(old, new, diff, "trust_zones", _ZONE_FIELDS)
    _diff_dict_section(old, new, diff, "confirmation_classes", _CC_FIELDS)
    _diff_list_section(old, new, diff, "side_effect_surfaces", key_field="action")
    _diff_list_section(old, new, diff, "transition_policies", key_field=None)

    return diff


# ── Section diffing ───────────────────────────────────────────────────────────

# Fields to compare per section (security-relevant fields highlighted)
_ACTION_FIELDS = [
    "reversible", "side_effects", "action_class", "risk_class",
    "required_capabilities", "requires_approval", "irreversible",
    "external_boundary", "taint_passthrough", "confirmation_class",
]
_ACTOR_FIELDS = ["type", "trust_tier", "permission_scope"]
_DC_FIELDS = ["taint_label", "confirmation", "retention"]
_ZONE_FIELDS = ["default_trust", "entities"]
_CC_FIELDS = ["blocking"]


def _diff_actions(old: dict, new: dict, diff: ManifestDiff) -> None:
    old_actions: dict = old.get("actions", {})
    new_actions: dict = new.get("actions", {})

    # Handle v1 format where actions is a list
    if isinstance(old_actions, list):
        old_actions = {a["name"]: a for a in old_actions}
    if isinstance(new_actions, list):
        new_actions = {a["name"]: a for a in new_actions}

    for name in sorted(set(old_actions) - set(new_actions)):
        diff.changes.append(ManifestChange("actions", REMOVED, name, ""))

    for name in sorted(set(new_actions) - set(old_actions)):
        diff.changes.append(ManifestChange("actions", ADDED, name, ""))

    for name in sorted(set(old_actions) & set(new_actions)):
        old_spec = old_actions[name]
        new_spec = new_actions[name]
        for f in _ACTION_FIELDS:
            ov = old_spec.get(f)
            nv = new_spec.get(f)
            if ov != nv:
                diff.changes.append(
                    ManifestChange("actions", CHANGED, name, f, ov, nv)
                )


def _diff_trust_channels(old: dict, new: dict, diff: ManifestDiff) -> None:
    old_ch: dict = old.get("trust_channels", {})
    new_ch: dict = new.get("trust_channels", {})

    # v1: trust_channels is a list of {name, trust_level, taint_by_default}
    if isinstance(old_ch, list):
        old_ch = {c["name"]: c for c in old_ch}
    if isinstance(new_ch, list):
        new_ch = {c["name"]: c for c in new_ch}

    for name in sorted(set(old_ch) - set(new_ch)):
        diff.changes.append(ManifestChange("trust_channels", REMOVED, name, ""))

    for name in sorted(set(new_ch) - set(old_ch)):
        diff.changes.append(ManifestChange("trust_channels", ADDED, name, ""))

    for name in sorted(set(old_ch) & set(new_ch)):
        for f in ("trust_level", "taint_by_default"):
            ov = old_ch[name].get(f)
            nv = new_ch[name].get(f)
            if ov != nv:
                diff.changes.append(
                    ManifestChange("trust_channels", CHANGED, name, f, ov, nv)
                )


def _diff_capability_matrix(old: dict, new: dict, diff: ManifestDiff) -> None:
    old_matrix: dict = old.get("capability_matrix", {})
    new_matrix: dict = new.get("capability_matrix", {})

    all_tiers = sorted(set(old_matrix) | set(new_matrix))
    for tier in all_tiers:
        ov = sorted(old_matrix.get(tier, []) or [])
        nv = sorted(new_matrix.get(tier, []) or [])
        if ov != nv:
            diff.changes.append(
                ManifestChange("capability_matrix", CHANGED, tier, "capabilities", ov, nv)
            )


def _diff_taint_rules(old: dict, new: dict, diff: ManifestDiff) -> None:
    old_rules = old.get("taint_rules", []) or []
    new_rules = new.get("taint_rules", []) or []

    def _rule_key(r: dict) -> str:
        return f"{r.get('source_taint','')}.{r.get('operation','')}"

    old_map = {_rule_key(r): r for r in old_rules}
    new_map = {_rule_key(r): r for r in new_rules}

    for k in sorted(set(old_map) - set(new_map)):
        diff.changes.append(ManifestChange("taint_rules", REMOVED, k, ""))

    for k in sorted(set(new_map) - set(old_map)):
        diff.changes.append(ManifestChange("taint_rules", ADDED, k, ""))

    for k in sorted(set(old_map) & set(new_map)):
        ov = old_map[k].get("result")
        nv = new_map[k].get("result")
        if ov != nv:
            diff.changes.append(ManifestChange("taint_rules", CHANGED, k, "result", ov, nv))


def _diff_escalation_rules(old: dict, new: dict, diff: ManifestDiff) -> None:
    old_esc: dict = old.get("escalation_rules", old.get("escalation_conditions", {})) or {}
    new_esc: dict = new.get("escalation_rules", new.get("escalation_conditions", {})) or {}

    # v1 escalation_conditions is a list
    if isinstance(old_esc, list):
        old_esc = {e["id"]: e for e in old_esc}
    if isinstance(new_esc, list):
        new_esc = {e["id"]: e for e in new_esc}

    for name in sorted(set(old_esc) - set(new_esc)):
        diff.changes.append(ManifestChange("escalation_rules", REMOVED, name, ""))

    for name in sorted(set(new_esc) - set(old_esc)):
        diff.changes.append(ManifestChange("escalation_rules", ADDED, name, ""))


def _diff_dict_section(
    old: dict,
    new: dict,
    diff: ManifestDiff,
    section: str,
    fields: list[str],
) -> None:
    old_sec: dict = old.get(section, {}) or {}
    new_sec: dict = new.get(section, {}) or {}

    for name in sorted(set(old_sec) - set(new_sec)):
        diff.changes.append(ManifestChange(section, REMOVED, name, ""))

    for name in sorted(set(new_sec) - set(old_sec)):
        diff.changes.append(ManifestChange(section, ADDED, name, ""))

    for name in sorted(set(old_sec) & set(new_sec)):
        for f in fields:
            ov = _normalize(old_sec[name].get(f))
            nv = _normalize(new_sec[name].get(f))
            if ov != nv:
                diff.changes.append(ManifestChange(section, CHANGED, name, f, ov, nv))


def _diff_list_section(
    old: dict,
    new: dict,
    diff: ManifestDiff,
    section: str,
    key_field: str | None,
) -> None:
    old_list: list = old.get(section, []) or []
    new_list: list = new.get(section, []) or []

    if key_field:
        old_map = {item[key_field]: item for item in old_list if key_field in item}
        new_map = {item[key_field]: item for item in new_list if key_field in item}

        for k in sorted(set(old_map) - set(new_map)):
            diff.changes.append(ManifestChange(section, REMOVED, k, ""))
        for k in sorted(set(new_map) - set(old_map)):
            diff.changes.append(ManifestChange(section, ADDED, k, ""))
        for k in sorted(set(old_map) & set(new_map)):
            if old_map[k] != new_map[k]:
                diff.changes.append(ManifestChange(section, CHANGED, k, ""))
    else:
        # No key field: compare by position or set membership
        old_set = {_frozen(item) for item in old_list}
        new_set = {_frozen(item) for item in new_list}
        added_count = len(new_set - old_set)
        removed_count = len(old_set - new_set)
        if added_count:
            diff.changes.append(
                ManifestChange(section, ADDED, f"{added_count} entries", "")
            )
        if removed_count:
            diff.changes.append(
                ManifestChange(section, REMOVED, f"{removed_count} entries", "")
            )


def _normalize(val: Any) -> Any:
    """Normalize a value for comparison (sort lists, etc.)."""
    if isinstance(val, list):
        return sorted(str(v) for v in val)
    return val


def _frozen(item: Any) -> str:
    """Return a stable string representation of a dict for set membership."""
    if isinstance(item, dict):
        return str(sorted(item.items()))
    return str(item)
