"""
action_resolver.py — Deterministic raw-tool-call to logical-action resolver.

INV-003: Raw tool call must resolve to exactly one logical action or deny.
INV-013: Input normalisation is strict and type-safe.

Rules:
  - Non-string / empty tool name => deny
  - Tool name not in predicate table => deny (INV-001 / INV-012)
  - Zero predicates match => deny
  - Two or more predicates match => deny (ambiguity is never allowed)
  - No fuzzy matching, no permissive fallback, no heuristic

All functions are pure (no side effects) and deterministic.
"""

from __future__ import annotations

from typing import Any

from ah_defense.policy_types import (
    CompiledManifest,
    NormalizedIntent,
    RawToolCall,
)


class ResolutionError(Exception):
    """Raised when a tool call cannot be resolved to a unique logical action.

    Always signals a deny outcome.
    """
    def __init__(self, message: str, reason_code: str, invariant: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.invariant = invariant


# ── Public API ────────────────────────────────────────────────────────────────

def extract_tool_name(tc: Any) -> str:
    """Strictly extract the tool/function name from a raw tool-call object.

    Accepts objects with a .function attribute (FunctionCall) or plain dicts.

    INV-013: Non-string or empty name raises ResolutionError.

    Raises:
        ResolutionError: If function is missing, not a string, or empty.
    """
    # Object-style (agentdojo FunctionCall)
    if hasattr(tc, "function"):
        raw = tc.function
    elif isinstance(tc, dict):
        raw = tc.get("function")
    else:
        raise ResolutionError(
            f"Tool-call object has unexpected type {type(tc).__name__}; cannot extract name",
            reason_code="INVALID_TOOL_CALL_TYPE",
            invariant="INV-013",
        )

    if raw is None:
        raise ResolutionError(
            "Tool call has no 'function' field",
            reason_code="MISSING_FUNCTION",
            invariant="INV-013",
        )

    if not isinstance(raw, str):
        raise ResolutionError(
            f"Tool function name must be str, got {type(raw).__name__}",
            reason_code="NON_STRING_TOOL_NAME",
            invariant="INV-013",
        )

    stripped = raw.strip()
    if not stripped:
        raise ResolutionError(
            "Tool function name is empty or whitespace-only",
            reason_code="EMPTY_TOOL_NAME",
            invariant="INV-013",
        )

    return stripped


def extract_tool_args(tc: Any) -> dict[str, Any]:
    """Strictly extract the args dict from a raw tool-call object.

    INV-013: If args are present but not a dict, raises ResolutionError.
    Missing args returns empty dict (valid — schema check handles required params).

    Raises:
        ResolutionError: If args field is present but not a mapping.
    """
    if hasattr(tc, "args"):
        raw = tc.args
    elif isinstance(tc, dict):
        raw = tc.get("args", {})
    else:
        raw = {}

    if raw is None:
        return {}

    if not isinstance(raw, dict):
        raise ResolutionError(
            f"Tool call args must be a dict, got {type(raw).__name__}",
            reason_code="INVALID_ARGS_TYPE",
            invariant="INV-013",
        )

    return raw


def normalize_tool_call_to_intent(
    raw: RawToolCall,
    manifest: CompiledManifest,
    source_channel: str = "unknown",
) -> NormalizedIntent:
    """Resolve a RawToolCall to exactly one NormalizedIntent using manifest predicates.

    INV-003: Exactly one predicate must match; 0 or 2+ => ResolutionError (=> deny).
    INV-001 / INV-012: Tool name not in predicate table => ResolutionError.

    Args:
        raw: The validated raw tool call (function_name already extracted).
        manifest: The compiled manifest (must be loaded; caller verifies).
        source_channel: Trust channel for this call.

    Returns:
        NormalizedIntent with the resolved action_name.

    Raises:
        ResolutionError: If resolution fails for any reason.
    """
    tool_name = raw.function_name
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ResolutionError(
            "function_name is invalid at normalisation stage",
            reason_code="INVALID_TOOL_NAME_AT_NORMALISE",
            invariant="INV-013",
        )

    tool_name = tool_name.strip()

    # INV-001 / INV-012: tool not in predicate table => deny
    if tool_name not in manifest.tool_predicates:
        raise ResolutionError(
            f"Tool '{tool_name}' has no predicate definition in manifest ontology",
            reason_code="UNKNOWN_TOOL",
            invariant="INV-001",
        )

    predicate_list = manifest.tool_predicates[tool_name]
    args = raw.raw_args

    matched: list[str] = []
    for pred in predicate_list:
        if _predicate_matches(pred["match"], args):
            matched.append(pred["action"])

    if len(matched) == 0:
        raise ResolutionError(
            f"Tool '{tool_name}': no predicate matched args {list(args.keys())}",
            reason_code="NO_PREDICATE_MATCH",
            invariant="INV-003",
        )

    if len(matched) > 1:
        raise ResolutionError(
            f"Tool '{tool_name}': ambiguous — {len(matched)} predicates matched: {matched}",
            reason_code="AMBIGUOUS_PREDICATE_MATCH",
            invariant="INV-003",
        )

    return NormalizedIntent(
        raw_tool_name=tool_name,
        action_name=matched[0],
        args=args,
        call_id=raw.call_id,
        source_channel=source_channel,
    )


def make_raw_tool_call(tc: Any) -> RawToolCall:
    """Build a RawToolCall from a tool-call object, raising ResolutionError on failure.

    Combines extract_tool_name + extract_tool_args.

    Raises:
        ResolutionError: If extraction fails.
    """
    # call_id
    if hasattr(tc, "id"):
        call_id = str(tc.id)
    elif isinstance(tc, dict):
        call_id = str(tc.get("id", "unknown"))
    else:
        call_id = "unknown"

    tool_name = extract_tool_name(tc)    # may raise ResolutionError
    args = extract_tool_args(tc)          # may raise ResolutionError

    return RawToolCall(
        function_name=tool_name,
        raw_args=args,
        call_id=call_id,
    )


# ── Internal predicate engine ─────────────────────────────────────────────────

def _predicate_matches(match_cfg: dict[str, Any], args: dict[str, Any]) -> bool:
    """Return True if match_cfg is satisfied by args.

    Supported matchers (deterministic, strict):
      {}               — always matches (unconditional)
      arg_present: X   — args[X] exists and is truthy (non-empty list / non-empty string / etc.)
      arg_absent: X    — args[X] does not exist OR is falsy (None, [], "", 0)

    Unknown match keys => False (fail-closed; no fuzzy expansion).
    """
    if not match_cfg:
        return True

    for key, value in match_cfg.items():
        if key == "arg_present":
            if not _is_arg_present(args, str(value)):
                return False
        elif key == "arg_absent":
            if _is_arg_present(args, str(value)):
                return False
        else:
            # Unknown match condition => fail-closed: predicate does not match
            return False

    return True


def _is_arg_present(args: dict[str, Any], param: str) -> bool:
    """Return True if param is present in args and has a truthy value."""
    if param not in args:
        return False
    val = args[param]
    # Treat None, empty list, empty string, empty dict as absent
    if val is None:
        return False
    if isinstance(val, (list, dict, str)) and len(val) == 0:
        return False
    return True
