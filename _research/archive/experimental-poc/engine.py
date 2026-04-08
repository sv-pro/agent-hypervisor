"""
engine.py – deterministic enforcement engine.

Given a single trace step and a loaded World Manifest, the engine returns
one of three decisions:

    ALLOW            – step is within the declared capability profile.
    DENY             – step is outside the profile or violates a constraint.
    REQUIRE_APPROVAL – step is allowed in principle but needs explicit sign-off.

Decision logic (in priority order):
1. If the step is tainted AND the target resource is external → DENY.
   Taint is derived from input provenance (input_sources × input_trust),
   not read from the raw 'tainted' field in the step dict.
2. If the action appears in denied_actions → DENY.
3. If the action is not in allowed_actions → DENY (undefined = deny).
4. If the resource does not match any permitted_resources pattern → DENY.
5. If the input source trust level is lower than trust_required → DENY.
6. If the (action, resource) appears in approval_required → REQUIRE_APPROVAL.
7. Otherwise → ALLOW.

Resource pattern matching uses prefix matching with a trailing "*" wildcard
(e.g. "repo://local/*" matches "repo://local/staging" and
"repo://local/src/main.py").
"""

from __future__ import annotations

import fnmatch
from enum import Enum
from typing import Any

from awc.policy.taint import derive_source_taint


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


_TRUST_ORDER = {"trusted": 2, "conditional": 1, "untrusted": 0}
_EXTERNAL_SCHEMES = {"external://", "http://", "https://"}


def _is_external(resource: str) -> bool:
    return any(resource.startswith(s) for s in _EXTERNAL_SCHEMES)


def _matches_pattern(resource: str, pattern: str) -> bool:
    if fnmatch.fnmatch(resource, pattern):
        return True
    # "scheme://authority/*" should also match "scheme://authority" (no path component)
    if pattern.endswith("/*") and resource == pattern[:-2]:
        return True
    return False


def _resource_allowed(resource: str, permitted: list[str]) -> bool:
    return any(_matches_pattern(resource, p) for p in permitted)


def _trust_sufficient(input_sources: list[str], trust_required: str, input_trust_map: dict[str, str]) -> bool:
    required_level = _TRUST_ORDER.get(trust_required, 2)
    for src in input_sources:
        src_level = _TRUST_ORDER.get(input_trust_map.get(src, "untrusted"), 0)
        if src_level < required_level:
            return False
    return True


def evaluate_step(
    step: dict[str, Any],
    manifest: dict[str, Any],
    derived_taint: bool | None = None,
    taint_reasons: list[str] | None = None,
) -> tuple[Decision, str]:
    """
    Evaluate one trace step against a manifest.

    derived_taint: pre-computed taint value (e.g. from compute_trace_taint,
                   which also propagates taint through depends_on).
                   If None, taint is derived inline from input_sources.
                   The legacy 'tainted' field in the step dict is ignored.
    taint_reasons: human-readable explanation of why the step is tainted.

    Returns (Decision, reason_string).
    """
    action = step.get("tool") or step.get("action", "")
    resource = step.get("resource", "")
    input_sources = step.get("input_sources", [])

    input_trust_map: dict[str, str] = manifest.get("input_trust", {})

    # Derive taint from provenance if not pre-computed by the trace evaluator.
    if derived_taint is None:
        derived_taint, computed_reasons = derive_source_taint(input_sources, input_trust_map)
        if taint_reasons is None:
            taint_reasons = computed_reasons
    if taint_reasons is None:
        taint_reasons = []

    # Rule 1: tainted + external resource → always deny.
    # Taint is derived from provenance, not from a manually assigned flag.
    if derived_taint and _is_external(resource):
        reason_detail = "; ".join(taint_reasons) if taint_reasons else "provenance-derived taint"
        return Decision.DENY, (
            f"Tainted data cannot trigger external resource '{resource}' "
            f"(taint derived from: {reason_detail})."
        )

    # Rule 2: action in explicitly denied list
    for denied in manifest.get("denied_actions", []):
        if denied.get("action") in (action, "*"):
            return Decision.DENY, f"Action '{action}' is explicitly denied: {denied.get('reason', '')}."

    # Rule 3 + 4 + 5: check allowed_actions list
    allowed_entries = manifest.get("allowed_actions", [])
    matched_entry: dict | None = None
    for entry in allowed_entries:
        if entry.get("action") != action:
            continue
        if not _resource_allowed(resource, entry.get("permitted_resources", [])):
            continue
        matched_entry = entry
        break

    if matched_entry is None:
        return Decision.DENY, (
            f"Action '{action}' on resource '{resource}' is not registered in the "
            f"compiled boundary — undefined action, denied by policy."
        )

    # Rule 5: trust check
    if not _trust_sufficient(input_sources, matched_entry.get("trust_required", "trusted"), input_trust_map):
        return Decision.DENY, (
            f"Input sources {input_sources} do not meet trust requirement "
            f"'{matched_entry.get('trust_required')}' for action '{action}'."
        )

    # Rule 6: approval_required check
    for approval in manifest.get("approval_required", []):
        if approval.get("action") != action:
            continue
        if _matches_pattern(resource, approval.get("resource_pattern", "")):
            return Decision.REQUIRE_APPROVAL, (
                f"Action '{action}' on '{resource}' requires approval: "
                f"{approval.get('reason', '')}."
            )

    return Decision.ALLOW, f"Action '{action}' on '{resource}' is within the declared capability profile."
