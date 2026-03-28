"""
execution_plan.py — Minimal ExecutionPlan abstraction.

An ExecutionPlan describes *how* a validated task should be executed.
It carries no policy — policy enforcement is complete before a plan is
ever consulted. The World Kernel decides what is *possible*; the plan
decides how execution is structured within that boundary.

Three concrete types:

    ExecutionPlan         — abstract base
    DirectExecutionPlan   — existing behavior: delegate to tool adapter
    ProgramExecutionPlan  — future: execute a structured program in a sandbox

Relationship to the rest of the system:

    IRBuilder (runtime)      — checks constraints at construction time
    ProvenanceFirewall       — checks provenance rules
    PolicyEngine             — checks declarative YAML rules
         │
         ▼  verdict == "allow"
    ExecutionPlan dispatch   ← this module's abstraction lives here
         │
         ├── "direct"  → tool_def.adapter(raw_args)   (current behavior)
         └── "program" → ProgramExecutor.execute(plan) (future sandbox)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass(frozen=True)
class ExecutionPlan:
    """
    Abstract base for execution plans.

    Subclasses must define `plan_type` as a string literal.
    All plans are frozen (immutable) after construction.
    """

    plan_id: str

    @property
    def plan_type(self) -> str:
        """Identifies the execution strategy. Subclasses return a literal."""
        raise NotImplementedError


@dataclass(frozen=True)
class DirectExecutionPlan(ExecutionPlan):
    """
    Wraps the existing direct execution path.

    This is the default plan. Using it produces behaviour identical to
    what the system did before the program layer was introduced: the
    registered tool adapter is called directly with the validated args.

    No new logic. No new risk surface. A named wrapper for existing behaviour.
    """

    @property
    def plan_type(self) -> Literal["direct"]:
        return "direct"


@dataclass(frozen=True)
class ProgramExecutionPlan(ExecutionPlan):
    """
    Execution plan backed by a structured program.

    Future use: the program_source (or a program_id that references a
    registered program) drives execution inside a sandboxed environment
    rather than delegating to a single tool adapter.

    Fields:
        plan_id        — unique identifier for this plan instance
        program_source — the program text (stub: may be None in Phase 1)
        program_id     — optional id of a registered/reviewed program
    """

    program_source: Optional[str] = field(default=None)
    program_id: Optional[str] = field(default=None)

    @property
    def plan_type(self) -> Literal["program"]:
        return "program"
