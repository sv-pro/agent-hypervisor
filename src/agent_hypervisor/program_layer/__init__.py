"""
program_layer — Executable program abstraction layer.

This package is an optional, pluggable extension above the World Kernel that
allows execution to be driven by structured, linear programs rather than
direct tool adapter calls.

The World Kernel (runtime/, hypervisor/) is not modified.
All policy enforcement runs before any program layer code is reached.
Programs orchestrate; the World Kernel decides what is possible.

Phase 1 — Minimal Task Compiler + Safe Program Execution:

    Program / Step            — linear program model (no branches/loops).
                                Step gains an optional ``description`` field.
    ProgramTrace / StepTrace  — per-step execution trace (allow/deny/skip).
    ProgramRunner             — validates → compiles → executes step-by-step.
    SimpleTaskCompiler        — maps string/dict intents to ExecutionPlan via
                                keyword matching; falls back to DirectExecutionPlan.
    validate_program()        — static pre-execution world constraint check.
    ProgramTraceStore         — JSONL-backed persistent trace storage.
    ENABLE_PROGRAM_LAYER      — master feature flag.

Prior phase (sandbox foundations):
    SandboxRuntime            — restricted exec() (AST-validated, timeout).
    DeterministicTaskCompiler — converts named workflows to ProgramExecutionPlan.
    ProgramExecutor           — runs ProgramExecutionPlan in the sandbox.

Plan types:
    ExecutionPlan             — abstract base.
    DirectExecutionPlan       — existing direct execution (unchanged behavior).
    ProgramExecutionPlan      — sandbox execution (functional in Phase 1).

Protocols:
    TaskCompiler              — compile(intent, world) → ExecutionPlan.
    Executor                  — execute(plan, context) → result.
    ProgramRegistry           — stub for future reviewed-program store.

PL-3 — Program Review & Minimization:

    CandidateStep             — a step from a raw candidate program (from traces).
    ReviewedProgram           — the reviewed, minimized, replayable artifact.
    ProgramStatus             — lifecycle states (proposed/reviewed/accepted/rejected).
    ProgramDiff               — explicit diff of every minimization transformation.
    ProgramMetadata           — provenance (trace_id, world_version, created_at).
    RemovedStep               — records a step removed during minimization.
    ParamChange               — records a parameter reduction during minimization.
    CapabilityChange          — records a capability narrowing during minimization.
    Minimizer                 — deterministic minimization engine.
    ProgramStore              — JSON file-backed storage for ReviewedProgram.
    ReplayEngine              — replay minimized programs via ProgramRunner.
    propose_program()         — create a PROPOSED ReviewedProgram from steps.
    minimize_program()        — apply minimization, update store.
    review_program()          — proposed → reviewed transition.
    accept_program()          — reviewed → accepted (with world validation).
    reject_program()          — reviewed → rejected.
    InvalidTransitionError    — raised on illegal status transition.
    WorldValidationError      — raised when minimized steps fail world validation.
    make_program_id()         — generate a unique program id.

Public surface:
    All names in __all__ are stable across their respective phases.
    SandboxError hierarchy is exported for callers handling specific failures.
"""

from .config import ENABLE_PROGRAM_LAYER
from .execution_plan import DirectExecutionPlan, ExecutionPlan, ProgramExecutionPlan
from .interfaces import Executor, ProgramRegistry, TaskCompiler
from .minimizer import Minimizer
from .program_executor import ProgramExecutor
from .program_model import MAX_STEPS, Program, Step
from .program_runner import ProgramRunner
from .program_store import ProgramStore
from .program_trace import ProgramTrace, StepTrace
from .replay_engine import ReplayEngine
from .review_lifecycle import (
    InvalidTransitionError,
    WorldValidationError,
    accept_program,
    minimize_program,
    propose_program,
    reject_program,
    review_program,
)
from .review_models import (
    CapabilityChange,
    CandidateStep,
    ParamChange,
    ProgramDiff,
    ProgramMetadata,
    ProgramStatus,
    RemovedStep,
    ReviewedProgram,
    make_program_id,
)
from .sandbox_runtime import (
    SandboxError,
    SandboxRuntime,
    SandboxRuntimeError,
    SandboxSecurityError,
    SandboxTimeoutError,
)
from .simple_task_compiler import SimpleTaskCompiler
from .task_compiler import DeterministicTaskCompiler
from .trace_storage import ProgramTraceStore
from .world_validator import (
    StepViolation,
    ValidationResult,
    validate_program,
    validate_step,
)

__all__ = [
    # Feature flag
    "ENABLE_PROGRAM_LAYER",
    # Program model (Phase 1)
    "Step",
    "Program",
    "MAX_STEPS",
    # Execution trace
    "StepTrace",
    "ProgramTrace",
    # Runner
    "ProgramRunner",
    # Plan types
    "ExecutionPlan",
    "DirectExecutionPlan",
    "ProgramExecutionPlan",
    # Protocols
    "TaskCompiler",
    "Executor",
    "ProgramRegistry",
    # Compilers
    "DeterministicTaskCompiler",
    "SimpleTaskCompiler",
    # Executor
    "ProgramExecutor",
    # Sandbox
    "SandboxRuntime",
    "SandboxError",
    "SandboxSecurityError",
    "SandboxTimeoutError",
    "SandboxRuntimeError",
    # World validation
    "validate_program",
    "validate_step",
    "ValidationResult",
    "StepViolation",
    # Trace storage
    "ProgramTraceStore",
    # PL-3: Review models
    "CandidateStep",
    "ReviewedProgram",
    "ProgramStatus",
    "ProgramDiff",
    "ProgramMetadata",
    "RemovedStep",
    "ParamChange",
    "CapabilityChange",
    "make_program_id",
    # PL-3: Minimization
    "Minimizer",
    # PL-3: Storage
    "ProgramStore",
    # PL-3: Replay
    "ReplayEngine",
    # PL-3: Lifecycle functions
    "propose_program",
    "minimize_program",
    "review_program",
    "accept_program",
    "reject_program",
    # PL-3: Errors
    "InvalidTransitionError",
    "WorldValidationError",
]
