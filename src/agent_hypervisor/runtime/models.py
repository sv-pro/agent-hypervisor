"""
Base types for the runtime kernel.

This module contains only primitive enumerations and construction errors.
It has no imports from other runtime modules — it is the foundation layer.

Design notes:
  - TrustLevel replaces old string-based trust map lookups.
  - TaintState.join() makes taint monotonic and composable.
  - ConstructionError is the base class for all IR construction failures.
  - Typed subclasses (NonExistentAction, ConstraintViolation, TaintViolation,
    ApprovalRequired) let callers distinguish denial reasons without parsing
    message strings. Catching ConstructionError still works — it is the base.
"""

from enum import Enum


class ProvenanceVerdict(Enum):
    """
    The verdict produced by evaluating compiled provenance rules.

    Verdict precedence (highest wins when multiple rules match):
        deny > ask > allow

    Fail-closed default: if no rule matches, the runtime returns deny.
    """
    allow = "allow"
    deny  = "deny"
    ask   = "ask"


class CalibrationPolicy(Enum):
    """
    Compiled expansion policy for a single action.

    Controls whether a future calibration engine may consider capability
    expansion for this action. The compiled value is the authoritative
    ruling — future calibration code must not override it.

    Values:
        deny  — expansion is prohibited regardless of the request
        ask   — expansion requires explicit human review
        allow — expansion may be considered (subject to other constraints)

    Fail-closed: if no CalibrationPolicy is compiled for an action
    (i.e. calibration_constraint_for() returns None), calibration code
    must treat the absence as deny.
    """
    deny  = "deny"
    ask   = "ask"
    allow = "allow"


class ArgumentProvenance(Enum):
    """
    Provenance class of a value argument, ordered from least to most trusted.

    Mirrors hypervisor.models.ProvenanceClass but lives in the runtime kernel
    so compile.py has no import dependency on hypervisor/.

        external_document  — content from files, network, or agent outputs
        derived            — computed/extracted from one or more parents
        user_declared      — explicitly stated by the operator in the manifest
        system             — hardcoded by the system (no user influence)
    """
    external_document = "external_document"
    derived           = "derived"
    user_declared     = "user_declared"
    system            = "system"


class TaintState(Enum):
    CLEAN = "clean"
    TAINTED = "tainted"

    def join(self, other: "TaintState") -> "TaintState":
        """
        Taint lattice join (least upper bound).

        CLEAN  ∨ CLEAN   = CLEAN
        CLEAN  ∨ TAINTED = TAINTED
        TAINTED ∨ CLEAN  = TAINTED
        TAINTED ∨ TAINTED = TAINTED

        Taint is monotonic: it can only increase, never decrease.
        """
        if self is TaintState.TAINTED or other is TaintState.TAINTED:
            return TaintState.TAINTED
        return TaintState.CLEAN


class ActionType(Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class TrustLevel(Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


# ── Construction errors ───────────────────────────────────────────────────────
#
# All are subclasses of ConstructionError so callers can catch the base class
# without caring about the specific reason. Typed subclasses are available for
# callers that need to distinguish denial reasons without parsing strings.


class ConstructionError(Exception):
    """
    Base: raised when an IntentIR cannot be constructed.

    This is NOT a runtime denial. The IR cannot be formed because the
    requested combination of (action, trust, taint) is not representable
    in the compiled policy. No execution path is entered.

    Subclasses carry the specific reason:
      NonExistentAction  — action name not in the registered ontology
      ConstraintViolation — trust/capability constraint not satisfied
      TaintViolation     — taint rule fired (tainted data → external action)
      ApprovalRequired   — action requires an approval token (not yet supported)
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"ConstructionError: {reason}")


class NonExistentAction(ConstructionError):
    """
    The action name is not registered in the compiled policy.

    This is an ontological absence, not a policy denial. The action does
    not exist in this world — it cannot be represented as an IntentIR.
    """


class ConstraintViolation(ConstructionError):
    """
    The source's trust level does not satisfy the action's capability requirement.

    The action exists but the requesting source cannot perform it given
    the compiled capability matrix.
    """


class TaintViolation(ConstructionError):
    """
    A taint rule fired: tainted data cannot flow into this action.

    Typically: TAINTED context + EXTERNAL action → TaintViolation.
    The IR cannot be formed because construction would violate the taint policy.
    """


class ApprovalRequired(ConstructionError):
    """
    The action requires an approval token, which is not yet supported.

    This is an honest dead end: the feature is deferred. The action exists
    and the capability check passes, but construction is blocked until an
    approval mechanism is implemented.
    """


class BudgetExceeded(ConstructionError):
    """
    The estimated cost of the requested action exceeds the compiled budget limit.

    This is an economic boundary violation, not a security policy denial.
    The action exists and the capability/taint checks passed, but the declared
    budget does not cover the worst-case estimated cost.

    Attributes:
        estimated_cost: The conservative cost estimate that triggered this error (USD).
        budget_limit:   The applicable compiled budget limit (USD).
        replan_hint:    Optional structured suggestion for a cheaper alternative.
                        None when no cheaper path is structurally available.
    """

    def __init__(
        self,
        reason: str,
        estimated_cost: float,
        budget_limit: float,
        replan_hint: object | None = None,
    ) -> None:
        self.estimated_cost = estimated_cost
        self.budget_limit = budget_limit
        self.replan_hint = replan_hint
        super().__init__(reason)


class NonSimulatableAction(RuntimeError):
    """
    The action has no simulation binding in the compiled policy.

    Raised by SimulationExecutor when execute(ir) is called for an action
    whose action_name is not present in policy.simulation_bindings.

    This is a simulation-mode gap, not an ontological absence — the action
    exists and the IR was validly constructed; only the surrogate response
    is missing from the compiled artifact.
    """
