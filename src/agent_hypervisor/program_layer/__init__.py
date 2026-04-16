"""
program_layer — Optional execution abstraction layer (Phase 1).

This package introduces the Program Layer: an optional, pluggable extension
above the World Kernel that allows execution to be driven by structured
programs rather than direct tool adapter calls.

The World Kernel (runtime/, hypervisor/) is not modified.
All policy enforcement runs before any program layer code is reached.

Phase 1 additions (this release):
    Program / Step        — minimal linear program model (no branches/loops)
    ProgramTrace          — per-step execution trace (allow/deny/skip verdicts)
    ProgramRunner         — step-by-step executor: validates → compiles → runs
    ENABLE_PROGRAM_LAYER  — feature flag (env: AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER)

Phase 1 (sandbox foundations, from prior release):
    SandboxRuntime        — restricted exec() environment (AST-validated)
    DeterministicTaskCompiler — converts named workflows to ProgramExecutionPlan
    ProgramExecutor       — runs ProgramExecutionPlan in the sandbox

Existing (scaffolding from prior phase):
    ExecutionPlan         — base plan type
    DirectExecutionPlan   — wraps existing direct execution (default, unchanged)
    ProgramExecutionPlan  — code-based execution (now functional in Phase 1)
    TaskCompiler          — protocol: intent + world → ExecutionPlan
    Executor              — protocol: plan + context → result
    ProgramRegistry       — stub: store/load reviewed programs (future)

Public surface:
    All names in __all__ are stable across Phase 1.
    SandboxError hierarchy (SandboxSecurityError, SandboxTimeoutError,
    SandboxRuntimeError) is exported for callers that need to handle
    specific failure modes.
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
from .task_compiler import DeterministicTaskCompiler

__all__ = [
    # Feature flag
    "ENABLE_PROGRAM_LAYER",
    # Program model (Phase 1)
    "Step",
    "Program",
    "MAX_STEPS",
    # Execution trace (Phase 1)
    "StepTrace",
    "ProgramTrace",
    # Runner (Phase 1)
    "ProgramRunner",
    # Plan types
    "ExecutionPlan",
    "DirectExecutionPlan",
    "ProgramExecutionPlan",
    # Protocols
    "TaskCompiler",
    "Executor",
    "ProgramRegistry",
    # Implementations
    "ProgramExecutor",
    "SandboxRuntime",
    "DeterministicTaskCompiler",
    # Sandbox error hierarchy
    "SandboxError",
    "SandboxSecurityError",
    "SandboxTimeoutError",
    "SandboxRuntimeError",
]
