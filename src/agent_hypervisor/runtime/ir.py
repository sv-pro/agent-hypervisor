"""
Intent IR
=========

IntentIR is the ONLY form in which execution intent is expressed inside
the runtime. No natural language, no raw dicts, no action names as strings
reach the execution layer.

Sealing:
    IntentIR.__new__ checks for _IR_SEAL (module-private sentinel).
    External code cannot construct an IntentIR directly — TypeError at
    object creation. The only way to obtain an IntentIR is through
    IRBuilder.build().

Construction-time constraint checking (IRBuilder.build):
    All constraint evaluation happens HERE — at IR construction time.
    If build() raises ConstructionError, no execution path is entered.
    If build() returns an IntentIR, the action is valid and the Executor
    executes it without re-checking any constraint.

    Constraints checked at construction:
      1. Ontological: action must exist in compiled policy
      2. Capability: source trust level must permit the action type
      3. Approval: approval-required actions block construction (deferred)
      4. Taint propagation: taint is computed from required TaintContext
      5. Taint rule: TAINTED + EXTERNAL → ConstructionError
      6. Budget: estimated cost must not exceed compiled budget limits
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from .compile import CompiledAction, CompiledPolicy
from .channel import Source
from .models import (
    ActionType,
    ApprovalRequired,
    BudgetExceeded,
    ConstraintViolation,
    ConstructionError,
    NonExistentAction,
    TaintState,
    TaintViolation,
    TrustLevel,
)
from .taint import TaintContext, TaintedValue

if TYPE_CHECKING:
    from agent_hypervisor.economic.economic_policy import EconomicPolicyEngine
    from agent_hypervisor.economic.cost_estimator import CostEstimate


# ── Module-private IR seal ────────────────────────────────────────────────────
_IR_SEAL: object = object()


# ── IntentIR ──────────────────────────────────────────────────────────────────

class IntentIR:
    """
    A sealed, validated execution intent.

    Cannot be constructed outside IRBuilder.build(). The existence of an
    IntentIR object is proof that all constraints were satisfied at build time.

    Fields:
        action  : CompiledAction  — the action descriptor (metadata only, no handler)
        source  : Source          — the requesting identity (channel-derived, sealed)
        params  : dict            — execution parameters
        taint   : TaintState      — computed from TaintContext, not asserted by caller
    """

    __slots__ = ("action", "source", "params", "taint")

    def __new__(cls, *, _seal: object, **kwargs: Any) -> "IntentIR":
        if _seal is not _IR_SEAL:
            raise TypeError(
                "IntentIR cannot be constructed directly. "
                "Use IRBuilder.build() — construction validates all constraints."
            )
        return super().__new__(cls)

    def __init__(
        self,
        *,
        _seal: object,
        action: CompiledAction,
        source: Source,
        params: Dict[str, Any],
        taint: TaintState,
    ) -> None:
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "params", params)
        object.__setattr__(self, "taint", taint)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("IntentIR is immutable after construction")

    def __repr__(self) -> str:
        return (
            f"IntentIR("
            f"action={self.action.name!r}, "
            f"source={self.source.identity!r}, "
            f"taint={self.taint.value!r})"
        )


# ── IRBuilder ─────────────────────────────────────────────────────────────────

class IRBuilder:
    """
    Constructs IntentIR from validated inputs.

    All constraint checking happens inside build(). If build() returns,
    the IR is valid. If build() raises ConstructionError, the action is
    not representable — not denied at execution, not possible at all.

    Args:
        policy:          Compiled world policy (frozen, immutable).
        economic_engine: Optional budget enforcer. When provided alongside a
                         cost_estimate in build(), enforces budget limits as
                         constraint 6. Absent → budget check skipped (opt-in).
    """

    def __init__(
        self,
        policy: CompiledPolicy,
        economic_engine: Optional["EconomicPolicyEngine"] = None,
    ) -> None:
        self._policy = policy
        self._economic_engine = economic_engine

    def build(
        self,
        action_name: str,
        source: Source,
        params: Dict[str, Any],
        taint_context: TaintContext,
        cost_estimate: Optional["CostEstimate"] = None,
    ) -> IntentIR:
        """
        Build an IntentIR or raise ConstructionError.

        Parameters
        ----------
        action_name : str
            Must be present in the compiled policy.
        source : Source
            Must be obtained through Channel.source.
        params : dict
            Execution parameters passed to the action handler.
        taint_context : TaintContext
            Required. Cannot be omitted — callers cannot drop taint silently.
        cost_estimate : CostEstimate, optional
            When provided alongside an economic_engine, enforces budget limits
            at construction time (constraint 6). Omit to skip budget checking.
        """
        policy = self._policy

        # ── 1. Existence check against compiled action space ──────────────────
        # policy.action_space is the closed set: these and only these actions
        # exist in this compiled world. Absent name = impossible, not denied.
        action = policy.get_action(action_name)
        if action is None:
            raise NonExistentAction(
                f"Action {action_name!r} is not in the compiled action space "
                f"{sorted(policy.action_space)!r} — "
                f"absent actions are impossible in this world, not merely denied"
            )

        # ── 2. Capability check (O(1) frozenset lookup) ────────────────────────
        if not policy.can_perform(source.trust_level, action.action_type):
            raise ConstraintViolation(
                f"Trust level {source.trust_level.value!r} does not have capability "
                f"for {action.action_type.value!r} actions — IR cannot be formed"
            )

        # ── 3. Approval gate (deferred) ────────────────────────────────────────
        if action.approval_required:
            raise ApprovalRequired(
                f"Action {action_name!r} requires approval — "
                f"approval token support is deferred; IR construction blocked"
            )

        # ── 4. Taint from TaintContext (structural, not voluntary) ─────────────
        computed_taint = taint_context.taint

        # ── 5. Taint rule check ────────────────────────────────────────────────
        taint_rule = policy.taint_rule_for(computed_taint, action.action_type)
        if taint_rule is not None:
            raise TaintViolation(
                f"Taint rule violation: {taint_rule.reason} — IR cannot be formed"
            )

        # ── 6. Budget enforcement (opt-in) ─────────────────────────────────────
        # Requires both an economic_engine (set at IRBuilder construction) and a
        # cost_estimate (provided per-call). Either absent → budget check skipped.
        # evaluate_budget() raises BudgetExceeded (a ConstructionError) if the
        # estimate exceeds the compiled limit. Silent return means within budget.
        if self._economic_engine is not None and cost_estimate is not None:
            self._economic_engine.evaluate_budget(cost_estimate)

        return IntentIR(
            _seal=_IR_SEAL,
            action=action,
            source=source,
            params=params,
            taint=computed_taint,
        )
