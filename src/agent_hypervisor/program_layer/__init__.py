"""
program_layer — Executable program abstraction layer (Phase 1).

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

Public surface:
    All names in __all__ are stable across Phase 1.
    SandboxError hierarchy is exported for callers handling specific failures.
"""

from .config import ENABLE_PROGRAM_LAYER
from .execution_plan import DirectExecutionPlan, ExecutionPlan, ProgramExecutionPlan
from .interfaces import Executor, ProgramRegistry, TaskCompiler
from .program_executor import ProgramExecutor
from .program_model import MAX_STEPS, Program, Step
from .program_runner import ProgramRunner
from .program_trace import ProgramTrace, StepTrace
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
    # Program model
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
]
