"""
Taint Engine
============

TaintedValue[T] is the mandatory return type of all Executor.execute() calls.
TaintContext is the mandatory threading object for taint propagation across
pipeline stages. Callers must explicitly construct a TaintContext — taint
cannot be dropped by casual omission.

TaintContext semantics:
    - TaintContext.clean()              → CLEAN taint (first call, no prior data)
    - TaintContext.from_outputs(*tvs)   → taint join of all prior TaintedValues
    - TaintContext carries taint structurally; IRBuilder reads it at build time

Propagation rules:
    1. Every Executor.execute() returns TaintedValue — no exceptions.
    2. IRBuilder.build() accepts taint_context: TaintContext (required, not variadic).
    3. Taint join is monotonic: CLEAN ∨ TAINTED = TAINTED. Cannot decrease.
    4. TaintContext.clean() starts a new chain with CLEAN taint.
    5. TaintContext.from_outputs(*tvs) joins taint from all prior outputs.
    6. If the computed taint is TAINTED AND the action is EXTERNAL,
       IRBuilder raises ConstructionError — the IR cannot be formed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .models import TaintState

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class TaintedValue(Generic[T]):
    """
    A value paired with its taint state.

    This is the return type of all Executor.execute() calls.
    Taint cannot be removed from a TaintedValue — only propagated
    or joined with other TaintedValues via TaintContext.

    Use .map() to transform the value while preserving taint.
    Use TaintContext.from_outputs() to carry taint into the next build stage.
    """

    value: T
    taint: TaintState

    def map(self, f: Callable[[T], U]) -> "TaintedValue[U]":
        """Apply f to value, preserving taint state."""
        return TaintedValue(value=f(self.value), taint=self.taint)

    @staticmethod
    def join(*values: "TaintedValue") -> TaintState:
        """
        Compute the taint join across zero or more TaintedValues.

        join() with no arguments returns CLEAN (identity element).
        join() with any TAINTED argument returns TAINTED.
        Taint is monotonic: once introduced, it cannot be removed.
        """
        result = TaintState.CLEAN
        for v in values:
            result = result.join(v.taint)
        return result

    def __repr__(self) -> str:
        return f"TaintedValue(taint={self.taint.value!r}, value={self.value!r})"


class TaintContext:
    """
    Mandatory threading object for taint propagation between pipeline stages.

    TaintContext is the required argument to IRBuilder.build(). Callers cannot
    omit it — Python raises TypeError if they try. This closes the taint-drop
    gap that existed when *input_taints was variadic.

    Construction:
        TaintContext.clean()              — explicit CLEAN start (first action)
        TaintContext.from_outputs(*tvs)   — derives taint from prior executor outputs
    """

    __slots__ = ("_taint",)

    def __init__(self, taint: TaintState) -> None:
        object.__setattr__(self, "_taint", taint)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("TaintContext is immutable after construction")

    @staticmethod
    def clean() -> "TaintContext":
        """
        Construct a CLEAN TaintContext for pipeline entry points.

        Use this for the first action in a chain where no prior tainted
        output exists. Explicitly signals intent: this is a fresh start.
        """
        return TaintContext(TaintState.CLEAN)

    @staticmethod
    def from_outputs(*outputs: TaintedValue) -> "TaintContext":
        """
        Derive a TaintContext from one or more prior executor outputs.

        Computes the monotonic taint join across all outputs. If any output
        is TAINTED, the resulting TaintContext is TAINTED.
        """
        return TaintContext(TaintedValue.join(*outputs))

    @property
    def taint(self) -> TaintState:
        """The computed taint state carried by this context."""
        return self._taint

    def __repr__(self) -> str:
        return f"TaintContext(taint={self._taint.value!r})"
