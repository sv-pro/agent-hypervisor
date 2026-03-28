"""
program_layer — Optional execution abstraction layer.

This package introduces the Program Layer: an optional, pluggable extension
above the World Kernel that allows execution to be driven by structured
programs rather than direct tool adapter calls.

The World Kernel (runtime/, hypervisor/) is not modified.
All policy enforcement runs before any program layer code is reached.

Public surface:
    ExecutionPlan         — base plan type
    DirectExecutionPlan   — wraps existing direct execution (default)
    ProgramExecutionPlan  — code-based execution (future)
    TaskCompiler          — protocol: intent + world → ExecutionPlan
    Executor              — protocol: plan + context → result
    ProgramRegistry       — stub: store/load reviewed programs
    ProgramExecutor       — stub executor for ProgramExecutionPlan
"""

from .execution_plan import DirectExecutionPlan, ExecutionPlan, ProgramExecutionPlan
from .interfaces import Executor, ProgramRegistry, TaskCompiler
from .program_executor import ProgramExecutor

__all__ = [
    "ExecutionPlan",
    "DirectExecutionPlan",
    "ProgramExecutionPlan",
    "TaskCompiler",
    "Executor",
    "ProgramRegistry",
    "ProgramExecutor",
]
