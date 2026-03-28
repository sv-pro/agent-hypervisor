"""
program_layer — Optional execution abstraction layer (Phase 1).

This package introduces the Program Layer: an optional, pluggable extension
above the World Kernel that allows execution to be driven by structured
programs rather than direct tool adapter calls.

The World Kernel (runtime/, hypervisor/) is not modified.
All policy enforcement runs before any program layer code is reached.

New in Phase 1 (this release):
    SandboxRuntime        — restricted exec() environment (AST-validated)
    DeterministicTaskCompiler — converts named workflows to ProgramExecutionPlan
    ProgramExecutor       — runs ProgramExecutionPlan in the sandbox (real impl)

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

from .execution_plan import DirectExecutionPlan, ExecutionPlan, ProgramExecutionPlan
from .interfaces import Executor, ProgramRegistry, TaskCompiler
from .program_executor import ProgramExecutor
from .sandbox_runtime import (
    SandboxError,
    SandboxRuntime,
    SandboxRuntimeError,
    SandboxSecurityError,
    SandboxTimeoutError,
)
from .task_compiler import DeterministicTaskCompiler

__all__ = [
    # Plan types
    "ExecutionPlan",
    "DirectExecutionPlan",
    "ProgramExecutionPlan",
    # Protocols
    "TaskCompiler",
    "Executor",
    "ProgramRegistry",
    # Implementations (Phase 1)
    "ProgramExecutor",
    "SandboxRuntime",
    "DeterministicTaskCompiler",
    # Sandbox error hierarchy
    "SandboxError",
    "SandboxSecurityError",
    "SandboxTimeoutError",
    "SandboxRuntimeError",
]
