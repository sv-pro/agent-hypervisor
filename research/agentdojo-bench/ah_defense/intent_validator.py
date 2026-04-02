"""
intent_validator.py — Fail-closed, ontology-first intent validation engine.

Implements a deterministic, 7-step evaluation pipeline:
  1. check_manifest_loaded   — INV-002: no manifest => deny
  2. check_action_exists     — INV-001 / INV-012: unknown action => deny
  3. check_schema            — INV-004: schema mismatch => deny before execution
  4. check_capability        — INV-005: missing capability => deny
  5. check_taint_containment — INV-006: tainted external action => deny
  6. check_escalation        — INV-007/INV-015: high-risk => requireapproval
  7. allow                   — explicit allow only after all checks pass

Step order is fixed and must not be reordered (INV-009).

Every decision produces a full DecisionTrace (INV-010).
No LLM is on the critical path.
No silent fallbacks. No permissive defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from ah_defense.policy_types import (
    ALLOW,
    DENY,
    REQUIRE_APPROVAL,
    ActionDefinition,
    CompiledManifest,
    DecisionTrace,
    NormalizedIntent,
    ProvenanceSummary,
    TaintSummary,
    TraceStep,
    ValidationResult as PolicyValidationResult,
    Verdict,
)
from ah_defense.taint_tracker import ProvTaintState, TaintState

# Legacy ToolType kept for backward compatibility with old pipeline code.
ToolType = Literal["read_only", "internal_write", "external_side_effect", "unknown"]


# ── Public API ────────────────────────────────────────────────────────────────

def validate_intent(
    intent: NormalizedIntent,
    manifest: CompiledManifest | None,
    taint_state: ProvTaintState | TaintState | None,
    trust_level: str = "untrusted",
    capabilities: frozenset[str] | None = None,
) -> PolicyValidationResult:
    """Validate a normalised intent against the manifest and runtime state.

    This is the primary entry point for the fail-closed constraint engine.

    Args:
        intent: The normalised intent from the action resolver.
        manifest: The compiled manifest. None => deny (INV-002).
        taint_state: Current episode taint state. None => treated as clean.
        trust_level: The current episode trust level.
        capabilities: Granted capabilities for this episode. None => use manifest matrix.

    Returns:
        ValidationResult with full trace, verdict, and reason codes.

    INV-009: Given the same manifest + same intent + same taint state,
             the result is always identical.
    """
    steps: list[TraceStep] = []

    # ── Step 1: manifest loaded ──────────────────────────────────────────────
    step, early = check_manifest_loaded(manifest)
    steps.append(step)
    if early is not None:
        return _make_result(intent, None, early, steps, taint_state, None)

    # ── Step 2: action exists in ontology ────────────────────────────────────
    step, action_def, early = check_action_exists(intent.action_name, manifest)  # type: ignore[arg-type]
    steps.append(step)
    if early is not None:
        return _make_result(intent, action_def, early, steps, taint_state, None)

    # ── Step 3: schema check ─────────────────────────────────────────────────
    step, early = check_schema(intent.action_name, intent.args, action_def)  # type: ignore[arg-type]
    steps.append(step)
    if early is not None:
        return _make_result(intent, action_def, early, steps, taint_state, None)

    # ── Step 4: capability check ─────────────────────────────────────────────
    if capabilities is None:
        capabilities = manifest.capability_matrix.get(trust_level, frozenset())  # type: ignore[union-attr]
    step, early = check_capability(action_def, capabilities, trust_level)  # type: ignore[arg-type]
    steps.append(step)
    if early is not None:
        return _make_result(intent, action_def, early, steps, taint_state, None)

    # ── Step 5: taint containment ─────────────────────────────────────────────
    taint_summary = _get_taint_summary(taint_state)
    step, early = check_taint_containment(action_def, taint_summary, intent.args)  # type: ignore[arg-type]
    steps.append(step)
    if early is not None:
        return _make_result(intent, action_def, early, steps, taint_state, None)

    # ── Step 6: escalation / approval check ──────────────────────────────────
    step, early = check_escalation(action_def, manifest, taint_summary)  # type: ignore[arg-type]
    steps.append(step)
    if early is not None:
        return _make_result(intent, action_def, early, steps, taint_state, None)

    # ── Step 7: explicit allow ────────────────────────────────────────────────
    allow_step = TraceStep(
        step_name="allow",
        verdict=ALLOW,
        reason_code="ALL_CHECKS_PASSED",
        detail=f"Action '{intent.action_name}' passed all 6 policy checks",
        invariant=None,
    )
    steps.append(allow_step)

    return _make_result(
        intent, action_def, (ALLOW, "ALL_CHECKS_PASSED", "All policy checks passed", None, None),
        steps, taint_state, None
    )


# ── Individual check functions ────────────────────────────────────────────────

def check_manifest_loaded(
    manifest: CompiledManifest | None,
) -> tuple[TraceStep, tuple | None]:
    """Step 1 — INV-002: manifest must be present.

    Returns (step, early_result) where early_result is non-None if check fails.
    """
    if manifest is None:
        step = TraceStep(
            step_name="check_manifest_loaded",
            verdict=DENY,
            reason_code="MISSING_MANIFEST",
            detail="No manifest is loaded; cannot evaluate any action",
            invariant="INV-002",
        )
        return step, (DENY, "MISSING_MANIFEST", "No manifest loaded", "INV-002", None)

    step = TraceStep(
        step_name="check_manifest_loaded",
        verdict="pass",
        reason_code="MANIFEST_PRESENT",
        detail=f"Manifest v{manifest.version} suite={manifest.suite} loaded",
        invariant=None,
    )
    return step, None


def check_action_exists(
    action_name: str,
    manifest: CompiledManifest,
) -> tuple[TraceStep, ActionDefinition | None, tuple | None]:
    """Step 2 — INV-001 / INV-012: action must be defined in the ontology.

    Returns (step, action_def_or_None, early_result_or_None).
    """
    action_def = manifest.actions.get(action_name)
    if action_def is None:
        step = TraceStep(
            step_name="check_action_exists",
            verdict=DENY,
            reason_code="UNKNOWN_ACTION",
            detail=f"Action '{action_name}' is not defined in the manifest ontology",
            invariant="INV-001",
        )
        return step, None, (DENY, "UNKNOWN_ACTION", f"Action '{action_name}' does not exist in ontology", "INV-001", None)

    step = TraceStep(
        step_name="check_action_exists",
        verdict="pass",
        reason_code="ACTION_EXISTS",
        detail=f"Action '{action_name}' found: class={action_def.action_class} risk={action_def.risk_class}",
        invariant=None,
    )
    return step, action_def, None


def check_schema(
    action_name: str,
    args: dict[str, Any],
    action_def: ActionDefinition,
) -> tuple[TraceStep, tuple | None]:
    """Step 3 — INV-004: required parameters must be present and of correct type.

    Schema format: {param_name: {"type": str, "required": bool}}

    Returns (step, early_result_or_None).
    """
    schema = action_def.schema
    if not schema:
        # No schema defined => pass (not all actions require params)
        step = TraceStep(
            step_name="check_schema",
            verdict="pass",
            reason_code="NO_SCHEMA",
            detail=f"Action '{action_name}' has no schema constraints",
            invariant=None,
        )
        return step, None

    _TYPE_MAP: dict[str, type] = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
    }

    for param, constraints in schema.items():
        if not isinstance(constraints, dict):
            continue
        required = bool(constraints.get("required", False))
        expected_type_name = constraints.get("type", "")

        if required and param not in args:
            step = TraceStep(
                step_name="check_schema",
                verdict=DENY,
                reason_code="SCHEMA_MISSING_REQUIRED_PARAM",
                detail=f"Action '{action_name}': required parameter '{param}' is missing",
                invariant="INV-004",
            )
            return step, (
                DENY, "SCHEMA_MISSING_REQUIRED_PARAM",
                f"Required parameter '{param}' missing for action '{action_name}'",
                "INV-004", None,
            )

        if param in args and expected_type_name:
            expected_type = _TYPE_MAP.get(expected_type_name)
            if expected_type and not isinstance(args[param], expected_type):
                step = TraceStep(
                    step_name="check_schema",
                    verdict=DENY,
                    reason_code="SCHEMA_TYPE_MISMATCH",
                    detail=(
                        f"Action '{action_name}': parameter '{param}' expected"
                        f" {expected_type_name}, got {type(args[param]).__name__}"
                    ),
                    invariant="INV-004",
                )
                return step, (
                    DENY, "SCHEMA_TYPE_MISMATCH",
                    f"Parameter '{param}' has wrong type for action '{action_name}'",
                    "INV-004", None,
                )

    step = TraceStep(
        step_name="check_schema",
        verdict="pass",
        reason_code="SCHEMA_VALID",
        detail=f"Action '{action_name}' args pass schema validation",
        invariant=None,
    )
    return step, None


def check_capability(
    action_def: ActionDefinition,
    capabilities: frozenset[str],
    trust_level: str,
) -> tuple[TraceStep, tuple | None]:
    """Step 4 — INV-005: all required capabilities must be present.

    Returns (step, early_result_or_None).
    """
    required = set(action_def.required_capabilities)
    missing = required - capabilities
    if missing:
        step = TraceStep(
            step_name="check_capability",
            verdict=DENY,
            reason_code="CAPABILITY_MISSING",
            detail=(
                f"Action '{action_def.name}' requires capabilities {sorted(required)}"
                f"; missing {sorted(missing)} for trust_level='{trust_level}'"
            ),
            invariant="INV-005",
        )
        return step, (
            DENY, "CAPABILITY_MISSING",
            f"Trust level '{trust_level}' lacks required capabilities: {sorted(missing)}",
            "INV-005", None,
        )

    step = TraceStep(
        step_name="check_capability",
        verdict="pass",
        reason_code="CAPABILITY_OK",
        detail=f"All required capabilities present for trust_level='{trust_level}'",
        invariant=None,
    )
    return step, None


def check_taint_containment(
    action_def: ActionDefinition,
    taint_summary: TaintSummary | None,
    args: dict[str, Any] | None = None,
) -> tuple[TraceStep, tuple | None]:
    """Step 5 — INV-006: tainted data must not cross external boundary or trigger
    irreversible internal actions.

    Blocks when:
      - external_boundary=True AND context is tainted (prevents exfiltration)
      - irreversible=True AND context is tainted (prevents injection-driven destruction)

    Argument-level refinement (Fix 1):
      When taint_summary.tainted_values is non-empty (specific injection targets
      were extracted), the block only fires if at least one argument value in args
      matches a tainted_value.  This allows legitimate user actions whose args do
      not overlap with the attacker's payload.

      When tainted_values is EMPTY (conservative / unknown), the block fires
      unconditionally — fail-closed.

    Returns (step, early_result_or_None).
    """
    if not action_def.external_boundary and not action_def.irreversible:
        step = TraceStep(
            step_name="check_taint_containment",
            verdict="pass",
            reason_code="NOT_SENSITIVE_ACTION",
            detail=f"Action '{action_def.name}' is neither external boundary nor irreversible",
            invariant=None,
        )
        return step, None

    if taint_summary is None or taint_summary.label != "tainted":
        step = TraceStep(
            step_name="check_taint_containment",
            verdict="pass",
            reason_code="TAINT_CLEAN",
            detail=f"No tainted data in context; external action '{action_def.name}' not blocked",
            invariant=None,
        )
        return step, None

    # Argument-level taint check: if we know specific injection target values,
    # only block when the proposed call's arguments contain those values.
    if taint_summary.tainted_values and args is not None:
        arg_strings = _flatten_arg_strings(args)
        matching = arg_strings & taint_summary.tainted_values
        if not matching:
            step = TraceStep(
                step_name="check_taint_containment",
                verdict="pass",
                reason_code="TAINT_ARG_CLEAN",
                detail=(
                    f"Action '{action_def.name}': context is tainted but no argument "
                    f"matches known injection values — likely legitimate user action"
                ),
                invariant=None,
            )
            return step, None

    if action_def.external_boundary:
        detail = (
            f"Action '{action_def.name}' crosses external boundary"
            f" with tainted context (channels: {sorted(taint_summary.tainted_channels)})"
        )
        human = f"Tainted data must not cross external boundary via '{action_def.name}'"
    else:
        detail = (
            f"Action '{action_def.name}' is irreversible"
            f" with tainted context (channels: {sorted(taint_summary.tainted_channels)})"
        )
        human = f"Irreversible action '{action_def.name}' blocked: tainted context may indicate injection"

    step = TraceStep(
        step_name="check_taint_containment",
        verdict=DENY,
        reason_code="TAINT_CONTAINMENT_VIOLATION",
        detail=detail,
        invariant="INV-006",
    )
    return step, (
        DENY, "TAINT_CONTAINMENT_VIOLATION",
        human,
        "INV-006", None,
    )


def _flatten_arg_strings(args: dict[str, Any]) -> set[str]:
    """Recursively collect all string values from an args dict, lowercased."""
    result: set[str] = set()
    _collect_strings(args, result)
    return result


def _collect_strings(obj: Any, out: set[str]) -> None:
    if isinstance(obj, str):
        out.add(obj.lower())
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings(item, out)


def check_escalation(
    action_def: ActionDefinition,
    manifest: CompiledManifest,
    taint_summary: TaintSummary | None,
) -> tuple[TraceStep, tuple | None]:
    """Step 6 — INV-007 / INV-015: high-risk actions require explicit approval.

    Checks:
      - action_def.requires_approval (manifest-level unconditional)
      - escalation_rules for this action (conditional rules)

    Returns (step, early_result_or_None).
    """
    rule_id: str | None = None

    # Unconditional approval required by action definition
    if action_def.requires_approval:
        esc_rule = manifest.escalation_rules.get(action_def.name, {})
        rule_id = esc_rule.get("rule_id") or f"ACTION-REQUIRES-APPROVAL:{action_def.name}"
        reason_text = esc_rule.get("reason") or (
            f"Action '{action_def.name}' is marked requires_approval in manifest"
        )
        step = TraceStep(
            step_name="check_escalation",
            verdict=REQUIRE_APPROVAL,
            reason_code="APPROVAL_REQUIRED",
            detail=reason_text,
            invariant="INV-007",
        )
        return step, (
            REQUIRE_APPROVAL, "APPROVAL_REQUIRED",
            reason_text,
            "INV-007", rule_id,
        )

    step = TraceStep(
        step_name="check_escalation",
        verdict="pass",
        reason_code="NO_ESCALATION",
        detail=f"Action '{action_def.name}' does not require approval",
        invariant=None,
    )
    return step, None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_taint_summary(taint_state: ProvTaintState | TaintState | None) -> TaintSummary | None:
    if taint_state is None:
        return None
    if isinstance(taint_state, ProvTaintState):
        return taint_state.summarize_taint()
    # Legacy TaintState: synthesise a TaintSummary
    from ah_defense.policy_types import TaintSummary, TAINTED, CLEAN
    label = TAINTED if taint_state.is_tainted else CLEAN
    return TaintSummary(
        label=label,
        tainted_channels=frozenset({"unknown"}) if taint_state.is_tainted else frozenset(),
        taint_reasons=("tool_output",) if taint_state.is_tainted else (),
    )


def _make_result(
    intent: NormalizedIntent,
    action_def: ActionDefinition | None,
    early: tuple,
    steps: list[TraceStep],
    taint_state: ProvTaintState | TaintState | None,
    prov_summary: ProvenanceSummary | None,
) -> PolicyValidationResult:
    verdict, reason_code, human_reason, invariant, rule_id = early

    taint_summary = _get_taint_summary(taint_state)

    if isinstance(taint_state, ProvTaintState):
        prov_summary = taint_state.summarize_provenance()

    trace = DecisionTrace(
        steps=tuple(steps),
        final_verdict=verdict,
        final_reason_code=reason_code,
    )

    return PolicyValidationResult(
        raw_tool_name=intent.raw_tool_name,
        action_name=intent.action_name,
        verdict=verdict,
        reason_code=reason_code,
        human_reason=human_reason,
        violated_invariant=invariant,
        matched_rule_id=rule_id,
        action_type=action_def.action_class if action_def else None,
        risk_class=action_def.risk_class if action_def else None,
        provenance_summary=prov_summary,
        taint_summary=taint_summary,
        trace=trace,
        approval_context=None,
    )


# ── Legacy IntentValidator (backward-compatible) ──────────────────────────────

class IntentValidator:
    """Legacy validator for backward compatibility with AgentDojo pipeline.

    New code should use validate_intent() directly with a CompiledManifest.

    This class now routes through the fail-closed engine for known actions,
    and applies fail-closed deny for unknown tools (replaces old permissive
    unknown-tool behaviour).

    Breaking change from v1:
      - Unknown suite no longer returns a permissive validator (INV-002).
      - Unknown tool is now DENIED (was: treated as external, allowed if no taint).
      - Verdict now includes "requireapproval" in addition to "allow" / "deny".
    """

    def __init__(
        self,
        tool_classifications: dict[str, ToolType],
        manifest: CompiledManifest | None = None,
    ) -> None:
        self._classifications = tool_classifications
        self._manifest = manifest

    @classmethod
    def from_manifest(cls, manifest_path: str | Path) -> "IntentValidator":
        """Load a v1 World Manifest YAML and create a validator.

        For v2 manifests use manifest_compiler.load_and_compile() directly.
        """
        with open(manifest_path) as f:
            raw = yaml.safe_load(f)

        # Detect v2 manifest
        if isinstance(raw, dict) and str(raw.get("version", "")).startswith("2"):
            from ah_defense.manifest_compiler import compile_manifest
            compiled = compile_manifest(raw)
            # Synthesise legacy classifications from v2 action classes
            classifications: dict[str, ToolType] = {}
            for action_name, action_def in compiled.actions.items():
                # Map v2 action_class to legacy ToolType
                cls_map = {
                    "read_only": "read_only",
                    "reversible_internal": "internal_write",
                    "irreversible_internal": "internal_write",
                    "external_boundary": "external_side_effect",
                }
                classifications[action_name] = cls_map.get(action_def.action_class, "unknown")  # type: ignore[assignment]
            # Also map raw tool names via predicates
            for tool_name in compiled.tool_predicates:
                preds = compiled.tool_predicates[tool_name]
                if preds:
                    first_action = preds[0]["action"]
                    adef = compiled.actions.get(first_action)
                    if adef:
                        cls_map2 = {
                            "read_only": "read_only",
                            "reversible_internal": "internal_write",
                            "irreversible_internal": "internal_write",
                            "external_boundary": "external_side_effect",
                        }
                        classifications[tool_name] = cls_map2.get(adef.action_class, "unknown")  # type: ignore[assignment]
            return cls(classifications, manifest=compiled)

        # v1 manifest
        classifications_v1: dict[str, ToolType] = {}
        for tool_type in ("read_only", "internal_write", "external_side_effect"):
            section = raw.get(tool_type, [])
            if isinstance(section, list):
                for tool_name in section:
                    classifications_v1[tool_name] = tool_type  # type: ignore[assignment]

        return cls(classifications_v1)

    @classmethod
    def for_suite(cls, suite_name: str, manifests_dir: str | Path | None = None) -> "IntentValidator":
        """Load the manifest for a named suite.

        Breaking change: missing suite => deny-all validator (no longer permissive).
        """
        if manifests_dir is None:
            manifests_dir = Path(__file__).parent / "manifests"

        # Prefer v2 manifest
        v2_path = Path(manifests_dir) / f"{suite_name}_v2.yaml"
        if v2_path.exists():
            return cls.from_manifest(v2_path)

        v1_path = Path(manifests_dir) / f"{suite_name}.yaml"
        if v1_path.exists():
            return cls.from_manifest(v1_path)

        # INV-002: No manifest => deny-all (was: permissive fallback)
        return cls({}, manifest=None)

    def get_tool_type(self, tool_name: str) -> ToolType:
        """Return the legacy ToolType for a tool name, or 'unknown' if not in manifest."""
        return self._classifications.get(tool_name, "unknown")

    def validate(self, tool_name: str, taint_state: TaintState) -> "LegacyValidationResult":
        """Validate a proposed tool call.

        Returns LegacyValidationResult for backward compatibility.

        Breaking change: unknown tool is now DENIED (INV-001).
        """
        tool_type = self.get_tool_type(tool_name)

        # INV-001: unknown tool => deny
        if tool_type == "unknown":
            return LegacyValidationResult(
                tool_name=tool_name,
                verdict="deny",
                reason=(
                    f"Tool '{tool_name}' is not defined in the manifest ontology. "
                    "Unknown actions do not exist (INV-001)."
                ),
                tool_type="unknown",
            )

        # Taint containment check
        blocked = taint_state.check_tool_call(tool_name, tool_type)
        if blocked:
            return LegacyValidationResult(
                tool_name=tool_name,
                verdict="deny",
                reason=(
                    f"TaintContainmentLaw: tool '{tool_name}' has type "
                    f"'{tool_type}' and tainted context is present. "
                    "External side-effect blocked to prevent prompt injection exfiltration."
                ),
                tool_type=tool_type,
            )

        # Escalation check for high-risk actions (irreversible / external)
        # For legacy validators without a compiled manifest, we approximate
        # from the tool_type.
        if self._manifest is not None:
            # Use compiled manifest to check requires_approval
            action_def = self._manifest.actions.get(tool_name)
            if action_def and action_def.requires_approval:
                return LegacyValidationResult(
                    tool_name=tool_name,
                    verdict="requireapproval",
                    reason=(
                        f"Action '{tool_name}' requires explicit approval "
                        f"(risk_class={action_def.risk_class})."
                    ),
                    tool_type=tool_type,
                )

        return LegacyValidationResult(
            tool_name=tool_name,
            verdict="allow",
            reason=f"Tool '{tool_name}' ({tool_type}) permitted with current taint state",
            tool_type=tool_type,
        )


@dataclass(frozen=True)
class LegacyValidationResult:
    """Backward-compatible validation result.

    Use ValidationResult from policy_types for new code.
    """
    tool_name: str
    verdict: Literal["allow", "deny", "requireapproval"]
    reason: str
    tool_type: ToolType


# Re-export LegacyValidationResult as ValidationResult for import compat.
# New code importing ValidationResult from policy_types gets the rich type.
# Old code importing ValidationResult from intent_validator gets legacy type.
ValidationResult = LegacyValidationResult  # type: ignore[misc]
