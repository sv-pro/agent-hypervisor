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
