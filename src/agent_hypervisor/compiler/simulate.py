"""simulate.py — Dry-run trace replay against a World Manifest v2.

Replays each tool call in a trace against a manifest without executing
real tools. Returns a SimulationResult containing a full decision table.

Decision logic for v2 manifests:
  1. Resolve tool name to action via predicates (if defined) or direct lookup
  2. Unknown action → DENY_ABSENT
  3. Check input taint (from ToolCall.safe flag or explicit input_sources)
     If tainted and action.external_boundary → DENY_POLICY
  4. Check required_capabilities against trust tier capabilities
     If capabilities not satisfied → DENY_POLICY
  5. If action.requires_approval → REQUIRE_APPROVAL
  6. Otherwise → ALLOW

The simulation is deterministic. The same trace + manifest always
produces the same decision table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .observe import ExecutionTrace, ToolCall

# Outcome constants
ALLOW = "ALLOW"
DENY_ABSENT = "DENY_ABSENT"
DENY_POLICY = "DENY_POLICY"
REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass
class SimDecision:
    """A single simulated decision for one tool call in a trace."""

    tool: str
    params: dict[str, Any]
    outcome: str  # ALLOW | DENY_ABSENT | DENY_POLICY | REQUIRE_APPROVAL
    reason: str
    action_name: str = ""  # resolved action name from manifest
    tainted: bool = False
    step_index: int = 0

    @property
    def allowed(self) -> bool:
        return self.outcome == ALLOW

    @property
    def denied(self) -> bool:
        return self.outcome in (DENY_ABSENT, DENY_POLICY)


@dataclass
class SimulationResult:
    """Decision table produced by replaying a trace against a manifest."""

    manifest_name: str
    trace_id: str
    decisions: list[SimDecision] = field(default_factory=list)

    @property
    def allowed_count(self) -> int:
        return sum(1 for d in self.decisions if d.outcome == ALLOW)

    @property
    def denied_count(self) -> int:
        return sum(1 for d in self.decisions if d.outcome in (DENY_ABSENT, DENY_POLICY))

    @property
    def approval_count(self) -> int:
        return sum(1 for d in self.decisions if d.outcome == REQUIRE_APPROVAL)

    @property
    def absent_count(self) -> int:
        return sum(1 for d in self.decisions if d.outcome == DENY_ABSENT)

    @property
    def policy_count(self) -> int:
        return sum(1 for d in self.decisions if d.outcome == DENY_POLICY)

    def denied_decisions(self) -> list[SimDecision]:
        return [d for d in self.decisions if d.denied]

    def allowed_decisions(self) -> list[SimDecision]:
        return [d for d in self.decisions if d.allowed]


def simulate_trace(trace: ExecutionTrace, manifest: dict[str, Any]) -> SimulationResult:
    """Replay a trace against a v2 manifest dict, returning a decision table.

    Args:
        trace:    Parsed ExecutionTrace with tool calls.
        manifest: Validated v2 manifest dict (from loader_v2.load()).

    Returns:
        SimulationResult with one SimDecision per tool call.
    """
    manifest_name = manifest.get("manifest", {}).get("name", "unknown")
    result = SimulationResult(manifest_name=manifest_name, trace_id=trace.workflow_id)

    for i, call in enumerate(trace.calls):
        decision = _evaluate_call(call, manifest, step_index=i)
        result.decisions.append(decision)

    return result


def simulate_steps(
    steps: list[dict[str, Any]], manifest: dict[str, Any], workflow_id: str = "ad-hoc"
) -> SimulationResult:
    """Simulate a list of raw step dicts (tool + params + optional tainted flag).

    Each step dict: {"tool": str, "params": dict, "tainted": bool (optional)}

    This is the entry point for ahc simulate when given inline steps rather
    than a trace file.
    """
    calls = [
        ToolCall(
            tool=s["tool"],
            params=s.get("params", {}),
            safe=not s.get("tainted", False),
        )
        for s in steps
    ]
    trace = ExecutionTrace(workflow_id=workflow_id, calls=calls)
    return simulate_trace(trace, manifest)


# ── Core evaluation ───────────────────────────────────────────────────────────


def _evaluate_call(
    call: ToolCall, manifest: dict[str, Any], step_index: int = 0
) -> SimDecision:
    """Evaluate a single ToolCall against a v2 manifest dict."""
    actions = manifest.get("actions", {})
    predicates = manifest.get("predicates", {})
    capability_matrix = manifest.get("capability_matrix", {})

    tainted = not call.safe

    # Step 1: resolve tool → action name via predicates or direct lookup
    action_name, resolution_note = _resolve_action(call, actions, predicates)

    if action_name is None:
        return SimDecision(
            tool=call.tool,
            params=call.params,
            outcome=DENY_ABSENT,
            reason=f"'{call.tool}' is not declared in this manifest",
            action_name="",
            tainted=tainted,
            step_index=step_index,
        )

    action_spec = actions[action_name]

    # Step 2: taint check — tainted input + external_boundary = deny
    if tainted and action_spec.get("external_boundary", False):
        return SimDecision(
            tool=call.tool,
            params=call.params,
            outcome=DENY_POLICY,
            reason="Tainted input cannot cross external boundary",
            action_name=action_name,
            tainted=True,
            step_index=step_index,
        )

    # Step 3: capability check
    required_caps = action_spec.get("required_capabilities", [])
    if required_caps:
        # Use TRUSTED capabilities as the baseline for simulation
        # (the actual trust level comes from the caller's channel at runtime)
        trusted_caps: list[str] = []
        for tier in ("TRUSTED", "trusted"):
            if tier in capability_matrix:
                trusted_caps = capability_matrix[tier]
                break

        missing = [c for c in required_caps if c not in trusted_caps]
        if missing:
            return SimDecision(
                tool=call.tool,
                params=call.params,
                outcome=DENY_POLICY,
                reason=f"Missing capabilities: {missing}",
                action_name=action_name,
                tainted=tainted,
                step_index=step_index,
            )

    # Step 4: approval gate
    if action_spec.get("requires_approval", False):
        return SimDecision(
            tool=call.tool,
            params=call.params,
            outcome=REQUIRE_APPROVAL,
            reason=f"Action '{action_name}' requires explicit approval",
            action_name=action_name,
            tainted=tainted,
            step_index=step_index,
        )

    # Step 5: allow
    confirmation = action_spec.get("confirmation_class", "auto")
    note = f"Permitted by manifest (confirmation: {confirmation})"
    if resolution_note:
        note = f"{note} [{resolution_note}]"

    return SimDecision(
        tool=call.tool,
        params=call.params,
        outcome=ALLOW,
        reason=note,
        action_name=action_name,
        tainted=tainted,
        step_index=step_index,
    )


def _resolve_action(
    call: ToolCall,
    actions: dict[str, Any],
    predicates: dict[str, Any],
) -> tuple[str | None, str]:
    """Resolve a raw tool call to a manifest action name.

    Returns (action_name, resolution_note).
    action_name is None if no match was found.
    resolution_note describes how the resolution was made (for audit trail).
    """
    tool = call.tool

    # Try predicates first
    if tool in predicates:
        preds = predicates[tool]
        for pred in preds:
            action = pred.get("action", "")
            match = pred.get("match", {})
            if _predicate_matches(call, match):
                if action in actions:
                    return action, f"predicate:{tool}"
                # predicate matched but action not in ontology — deny absent
                return None, ""
        # predicates defined but none matched
        return None, ""

    # Direct lookup: tool name == action name
    if tool in actions:
        return tool, "direct"

    # Try stripping common suffixes / prefixes for fuzzy matching
    # e.g. "get_unread_emails" might map to "read_emails_unread" in actions
    # This is intentionally conservative — only exact matches and predicates
    return None, ""


def _predicate_matches(call: ToolCall, match: dict[str, Any]) -> bool:
    """Return True if the predicate match conditions are satisfied for this call."""
    if not match:
        return True  # empty match = match all

    # arg_present: match if the named param is present and non-empty
    if "arg_present" in match:
        arg = match["arg_present"]
        val = call.params.get(arg)
        if not val:
            return False

    # arg_absent: match if the named param is absent or empty
    if "arg_absent" in match:
        arg = match["arg_absent"]
        val = call.params.get(arg)
        if val:
            return False

    # param_equals: match if a param equals a specific value
    if "param_equals" in match:
        for param_name, expected in match["param_equals"].items():
            if call.params.get(param_name) != expected:
                return False

    return True
