"""tune.py — Manifest edit suggestions for failing or over-restricted scenarios.

Given a manifest and one or more failing SimDecisions (DENY_ABSENT, DENY_POLICY,
or REQUIRE_APPROVAL), suggests the minimal manifest edits that would change the
outcome.

This is a design-time tool: it helps manifest authors iterate on a manifest
in response to simulation results, without reading source code.

All suggestions are deterministic — the same input always produces the same
suggestions. No LLM is used; suggestions are derived from the manifest structure
and the failure reason.

Suggestion types:
  - ADD_ACTION: add a missing action to the manifest
  - ADD_CAPABILITY: add a required capability to a trust tier
  - CHANGE_FIELD: change a specific action field (requires_approval, external_boundary, etc.)
  - ADD_PREDICATE: add a predicate entry to route the tool to an existing action

Usage:
    from compiler.tune import suggest_edits
    suggestions = suggest_edits(manifest, failing_decisions)
    for s in suggestions:
        print(s)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .simulate import DENY_ABSENT, DENY_POLICY, REQUIRE_APPROVAL, SimDecision

# Suggestion types
ADD_ACTION = "ADD_ACTION"
ADD_CAPABILITY = "ADD_CAPABILITY"
CHANGE_FIELD = "CHANGE_FIELD"
ADD_PREDICATE = "ADD_PREDICATE"
RELAX_TAINT = "RELAX_TAINT"


@dataclass(frozen=True)
class ManifestSuggestion:
    """A single suggested manifest edit."""

    kind: str      # ADD_ACTION | ADD_CAPABILITY | CHANGE_FIELD | ADD_PREDICATE | RELAX_TAINT
    section: str   # manifest section to edit
    key: str       # element to add/change
    field: str     # specific field, or "" for the whole element
    suggested_value: Any
    rationale: str
    # The failing step this suggestion addresses
    tool: str = ""
    action_name: str = ""

    def __str__(self) -> str:
        loc = f"{self.section}.{self.key}"
        if self.field:
            loc += f".{self.field}"
        return f"[{self.kind}] {loc} = {self.suggested_value!r}  # {self.rationale}"

    def yaml_patch(self) -> str:
        """Return a minimal YAML snippet showing the suggested change."""
        if self.kind == ADD_ACTION:
            return (
                f"actions:\n"
                f"  {self.key}:\n"
                f"    reversible: true  # TODO: set correctly\n"
                f"    side_effects: []  # TODO: set correctly\n"
                f"    action_class: TODO\n"
                f"    risk_class: low\n"
                f"    required_capabilities: []\n"
                f"    requires_approval: false\n"
                f"    irreversible: false\n"
                f"    external_boundary: false\n"
                f"    taint_passthrough: false\n"
                f"    confirmation_class: auto\n"
                f"    description: TODO — add description\n"
            )
        if self.kind == ADD_PREDICATE:
            return (
                f"predicates:\n"
                f"  {self.tool}:\n"
                f"    - action: {self.suggested_value}\n"
                f"      match: {{}}  # matches all calls; add conditions if needed\n"
            )
        if self.kind == ADD_CAPABILITY:
            return (
                f"capability_matrix:\n"
                f"  TRUSTED:\n"
                f"    - {self.suggested_value}  # add this capability\n"
            )
        if self.kind == CHANGE_FIELD:
            return (
                f"actions:\n"
                f"  {self.key}:\n"
                f"    {self.field}: {self.suggested_value}\n"
            )
        return f"# {self.rationale}"


@dataclass
class TuneResult:
    """Suggestions for resolving one or more failing decisions."""

    decisions_analyzed: int
    suggestions: list[ManifestSuggestion] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.suggestions)

    def __iter__(self):
        return iter(self.suggestions)

    def for_tool(self, tool: str) -> list[ManifestSuggestion]:
        return [s for s in self.suggestions if s.tool == tool]

    def summary(self) -> str:
        if not self.suggestions:
            return "No suggestions — decisions appear correct."
        kinds = {}
        for s in self.suggestions:
            kinds[s.kind] = kinds.get(s.kind, 0) + 1
        parts = [f"{v} {k}" for k, v in sorted(kinds.items())]
        return f"{len(self.suggestions)} suggestions: {', '.join(parts)}"


def suggest_edits(
    manifest: dict[str, Any],
    failing: list[SimDecision],
) -> TuneResult:
    """Suggest manifest edits that would resolve the given failing decisions.

    Args:
        manifest: Validated v2 manifest dict.
        failing:  List of SimDecisions with outcome != ALLOW.

    Returns:
        TuneResult containing ManifestSuggestion objects.
    """
    result = TuneResult(decisions_analyzed=len(failing))
    seen: set[str] = set()

    for decision in failing:
        suggestions = _suggest_for_decision(decision, manifest)
        for s in suggestions:
            key = f"{s.kind}:{s.section}:{s.key}:{s.field}:{s.suggested_value}"
            if key not in seen:
                seen.add(key)
                result.suggestions.append(s)

    return result


# ── Per-decision suggestion logic ─────────────────────────────────────────────


def _suggest_for_decision(
    decision: SimDecision, manifest: dict[str, Any]
) -> list[ManifestSuggestion]:
    if decision.outcome == DENY_ABSENT:
        return _suggest_absent(decision, manifest)
    if decision.outcome == DENY_POLICY:
        return _suggest_policy(decision, manifest)
    if decision.outcome == REQUIRE_APPROVAL:
        return _suggest_approval(decision, manifest)
    return []


def _suggest_absent(
    decision: SimDecision, manifest: dict[str, Any]
) -> list[ManifestSuggestion]:
    """Tool not declared in manifest at all."""
    tool = decision.tool
    actions = manifest.get("actions", {})
    if isinstance(actions, list):
        actions = {a["name"]: a for a in actions}

    suggestions: list[ManifestSuggestion] = []

    # Option 1: add the tool as a new action
    if tool not in actions:
        suggestions.append(ManifestSuggestion(
            kind=ADD_ACTION,
            section="actions",
            key=tool,
            field="",
            suggested_value=tool,
            rationale=(
                f"'{tool}' is not declared in the manifest. Add it to the "
                "action ontology if this tool should be permitted."
            ),
            tool=tool,
            action_name=tool,
        ))

    # Option 2: add a predicate mapping this tool to an existing similar action
    similar = _find_similar_action(tool, actions)
    if similar:
        suggestions.append(ManifestSuggestion(
            kind=ADD_PREDICATE,
            section="predicates",
            key=tool,
            field="",
            suggested_value=similar,
            rationale=(
                f"'{tool}' may map to existing action '{similar}'. "
                "Add a predicate entry if this tool is a variant of that action."
            ),
            tool=tool,
            action_name=similar,
        ))

    return suggestions


def _suggest_policy(
    decision: SimDecision, manifest: dict[str, Any]
) -> list[ManifestSuggestion]:
    """Tool declared but constraint violated."""
    tool = decision.tool
    action_name = decision.action_name
    actions = manifest.get("actions", {})
    if isinstance(actions, list):
        actions = {a["name"]: a for a in actions}

    suggestions: list[ManifestSuggestion] = []
    action_spec = actions.get(action_name, {})

    reason = decision.reason.lower()

    if "tainted" in reason and "external boundary" in reason:
        # Taint + external boundary = injection containment working correctly.
        # Suggest: if the intent is to allow this, either:
        # (a) set external_boundary=false (if the action doesn't actually cross the boundary)
        # (b) add a taint-clearing rule for the specific transformation
        if action_spec.get("external_boundary"):
            suggestions.append(ManifestSuggestion(
                kind=CHANGE_FIELD,
                section="actions",
                key=action_name,
                field="external_boundary",
                suggested_value=False,
                rationale=(
                    "Tainted input is blocked at external boundary. "
                    "If this action does not actually cross the external boundary, "
                    "set external_boundary: false. "
                    "WARNING: only do this if you are certain no external data leaves."
                ),
                tool=tool,
                action_name=action_name,
            ))
        suggestions.append(ManifestSuggestion(
            kind=RELAX_TAINT,
            section="taint_rules",
            key=f"tainted.{decision.tool}",
            field="result",
            suggested_value="clear",
            rationale=(
                "To allow this action with tainted input, add a taint_rule that "
                "clears taint for the specific transformation preceding this call. "
                "WARNING: only clear taint if you can prove the transformation "
                "removes all injected content."
            ),
            tool=tool,
            action_name=action_name,
        ))

    elif "missing capabilities" in reason:
        # Extract missing cap from reason string if possible
        cap_start = reason.find("[") + 1
        cap_end = reason.find("]")
        missing_cap_str = reason[cap_start:cap_end] if cap_start > 0 and cap_end > 0 else ""

        required_caps = action_spec.get("required_capabilities", [])
        for cap in required_caps:
            suggestions.append(ManifestSuggestion(
                kind=ADD_CAPABILITY,
                section="capability_matrix",
                key="TRUSTED",
                field="",
                suggested_value=cap,
                rationale=(
                    f"Action '{action_name}' requires capability '{cap}' which "
                    "is not in the TRUSTED tier. Add it to capability_matrix.TRUSTED "
                    "if this capability should be available."
                ),
                tool=tool,
                action_name=action_name,
            ))

    return suggestions


def _suggest_approval(
    decision: SimDecision, manifest: dict[str, Any]
) -> list[ManifestSuggestion]:
    """Action requires approval — suggest making it automatic if intended."""
    action_name = decision.action_name
    suggestions: list[ManifestSuggestion] = []

    if action_name:
        suggestions.append(ManifestSuggestion(
            kind=CHANGE_FIELD,
            section="actions",
            key=action_name,
            field="requires_approval",
            suggested_value=False,
            rationale=(
                f"Action '{action_name}' requires approval. "
                "Set requires_approval: false if this action should be "
                "permitted automatically for trusted callers. "
                "WARNING: irreversible actions should retain requires_approval: true."
            ),
            tool=decision.tool,
            action_name=action_name,
        ))

    return suggestions


# ── Similarity heuristics ─────────────────────────────────────────────────────


def _find_similar_action(tool: str, actions: dict[str, Any]) -> str | None:
    """Find an action in the manifest that is likely related to the given tool name.

    Uses simple substring matching. Returns the best match or None.
    """
    tool_lower = tool.lower().replace("_", " ")
    best: str | None = None
    best_score = 0

    for action_name in actions:
        action_lower = action_name.lower().replace("_", " ")
        # Count shared words
        tool_words = set(tool_lower.split())
        action_words = set(action_lower.split())
        shared = tool_words & action_words
        score = len(shared)
        if score > best_score:
            best_score = score
            best = action_name

    # Only return if there's a meaningful match (at least 1 shared word)
    return best if best_score >= 1 else None
