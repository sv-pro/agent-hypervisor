"""
dual_execution_demo.py — Phase 1 Program Layer: two execution modes, one system.

This demo shows the same system running in two modes:

    Mode 1 (DIRECT):
        The classic path. A tool adapter is called directly with validated args.
        Policy enforcement runs, then the adapter runs. One adapter, one result.
        This is the path every request takes today.

    Mode 2 (PROGRAM):
        The new path. A DeterministicTaskCompiler converts a named workflow into
        a ProgramExecutionPlan. ProgramExecutor runs that plan inside a bounded
        sandbox (restricted exec(), AST-validated, with a timeout).
        The sandbox exposes only explicit bindings: read_input, emit_result, etc.

Both modes:
    - Are subject to the same World Kernel constraints (policy, provenance, taint).
    - Produce structured results.
    - Record execution mode in the result.

What this demo does NOT show:
    - The gateway HTTP API (see execution_router.py for that integration).
    - A real tool adapter connected to actual external state.
    - LLM-generated programs (not implemented, not planned for Phase 1).

Run with:
    python examples/program_layer/dual_execution_demo.py
"""

from __future__ import annotations

import sys
import os

# Add src to path so we can import without installing the package.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "src", "agent_hypervisor"))

from program_layer import (
    DeterministicTaskCompiler,
    DirectExecutionPlan,
    ProgramExecutionPlan,
    ProgramExecutor,
    SandboxRuntime,
)


# ---------------------------------------------------------------------------
# Simulated tool adapter (stands in for a real registered tool)
# ---------------------------------------------------------------------------

def _simple_text_tool(args: dict) -> dict:
    """
    Toy tool adapter.  In a real system this would be registered in the
    gateway's ToolRegistry and called only after policy enforcement.

    Here we just simulate what the adapter does: process 'text' from args.
    """
    text = args.get("text", "")
    return {
        "word_count": len(text.split()),
        "char_count": len(text),
        "preview": text[:50],
    }


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def _result(label: str, value: object) -> None:
    print(f"  {label}: {value!r}")


# ---------------------------------------------------------------------------
# Mode 1: Direct execution
# ---------------------------------------------------------------------------

def demo_direct_execution(text: str) -> None:
    _section("MODE 1 — Direct Execution (existing path, unchanged)")

    # In the real system, this call would be preceded by:
    #   IRBuilder.build() → policy check → verdict == "allow"
    # Then execution_router._dispatch_execution("direct", tool_def, raw_args)
    # calls tool_def.adapter(raw_args) directly.
    #
    # Here we simulate that final step to show what direct execution looks like.

    plan = DirectExecutionPlan(plan_id="demo-direct-001")
    raw_args = {"text": text}

    print(f"\n  plan_type : {plan.plan_type!r}")
    print(f"  plan_id   : {plan.plan_id!r}")
    print(f"  → calling tool adapter directly with validated args")

    result = _simple_text_tool(raw_args)

    print(f"\n  Result:")
    for k, v in result.items():
        _result(f"    {k}", v)
    print(f"\n  [No sandbox. No timeout. Existing behavior, unchanged.]")


# ---------------------------------------------------------------------------
# Mode 2: Program execution via DeterministicTaskCompiler
# ---------------------------------------------------------------------------

def demo_program_execution_via_compiler(text: str) -> None:
    _section("MODE 2a — Program Execution (compiled workflow)")

    compiler = DeterministicTaskCompiler()
    executor = ProgramExecutor()

    # The compiler converts a named workflow intent into a ProgramExecutionPlan.
    # No LLM. No synthesis. The same intent always produces the same program.
    intent = {"workflow": "word_frequency", "top_n": 5}
    plan = compiler.compile(intent)

    print(f"\n  workflow        : {intent['workflow']!r}")
    print(f"  plan_type       : {plan.plan_type!r}")
    print(f"  plan_id         : {plan.plan_id!r}")
    print(f"  language        : {plan.language!r}")
    print(f"  timeout_seconds : {plan.timeout_seconds}")
    print(f"  allowed_bindings: {plan.allowed_bindings}")
    print(f"  compiled_by     : {plan.metadata.get('compiled_by')!r}")
    print(f"\n  Generated program:")
    for line in plan.program_source.splitlines():
        print(f"    {line}")

    result = executor.execute(plan, context={"input": text})

    print(f"\n  Result (ok={result['ok']}):")
    if result["ok"]:
        for k, v in result["result"].items():
            _result(f"    {k}", v)
    print(f"\n  execution_mode  : {result['execution_mode']!r}")
    print(f"  duration_seconds: {result['duration_seconds']}")


# ---------------------------------------------------------------------------
# Mode 2: Program execution via raw program_source
# ---------------------------------------------------------------------------

def demo_program_execution_raw(text: str) -> None:
    _section("MODE 2b — Program Execution (raw program_source)")

    executor = ProgramExecutor()

    # Caller supplies a raw program directly.
    # The sandbox validates and executes it.
    program = """\
text = read_input()
lines = text.splitlines()
non_empty = [ln for ln in lines if ln.strip()]
emit_result({
    "line_count": len(lines),
    "non_empty_lines": len(non_empty),
    "first_line": lines[0].strip() if lines else "",
})
"""

    plan = ProgramExecutionPlan(
        plan_id="demo-raw-001",
        program_source=program,
        language="python",
        allowed_bindings=("read_input", "emit_result"),
        timeout_seconds=5.0,
        metadata={"source": "demo_raw"},
    )

    print(f"\n  plan_type       : {plan.plan_type!r}")
    print(f"  allowed_bindings: {plan.allowed_bindings}")
    print(f"  Program:")
    for line in program.splitlines():
        print(f"    {line}")

    result = executor.execute(plan, context={"input": text})

    print(f"\n  Result (ok={result['ok']}):")
    if result["ok"]:
        for k, v in result["result"].items():
            _result(f"    {k}", v)


# ---------------------------------------------------------------------------
# Show that the sandbox blocks forbidden operations
# ---------------------------------------------------------------------------

def demo_sandbox_blocks_forbidden(text: str) -> None:
    _section("MODE 2c — Sandbox: forbidden operations are blocked")

    executor = ProgramExecutor()

    for label, program in [
        ("import statement",   "import os\nemit_result(os.getcwd())"),
        ("eval() call",        "emit_result(eval('1+1'))"),
        ("open() call",        "open('/etc/passwd')"),
        ("infinite loop",      "while True: pass"),
    ]:
        plan = ProgramExecutionPlan(
            plan_id=f"demo-blocked-{label[:4]}",
            program_source=program,
            allowed_bindings=("read_input", "emit_result"),
            timeout_seconds=0.1,
        )
        result = executor.execute(plan, context={"input": text})
        status = "BLOCKED" if not result["ok"] else "BUG: allowed"
        print(f"  [{status}] {label:20s} → error_type={result.get('error_type')!r}")


# ---------------------------------------------------------------------------
# Compare: same World Kernel, two execution paths
# ---------------------------------------------------------------------------

def demo_comparison_note() -> None:
    _section("KEY POINT — Same World Kernel, Different Execution Path")
    print("""
  BEFORE policy verdict:
    World Kernel enforces constraints (IRBuilder, ProvenanceFirewall,
    PolicyEngine, taint propagation).  This is IDENTICAL for both paths.
    Neither path can run until the World Kernel says "allow".

  AFTER policy verdict:
    Direct path:  tool_def.adapter(raw_args)
    Program path: ProgramExecutor → SandboxRuntime → bounded exec()

  The World Kernel defines WHAT IS POSSIBLE.
  The Program Layer defines HOW ONE SPECIFIC TASK EXECUTES.
  These two responsibilities remain completely separated.
    """)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

SAMPLE_TEXT = """\
The agent hypervisor enforces boundaries at design time.
Policy decisions are made before any code runs.
Programs may define how tasks are executed.
They may never define what is possible.
That remains defined by the World Kernel.
"""


def main() -> None:
    print("\n[Agent Hypervisor — Phase 1 Program Layer Demo]")
    print(f"Input text ({len(SAMPLE_TEXT.split())} words, {len(SAMPLE_TEXT.splitlines())} lines):")
    for line in SAMPLE_TEXT.strip().splitlines():
        print(f"  | {line}")

    demo_direct_execution(SAMPLE_TEXT)
    demo_program_execution_via_compiler(SAMPLE_TEXT)
    demo_program_execution_raw(SAMPLE_TEXT)
    demo_sandbox_blocks_forbidden(SAMPLE_TEXT)
    demo_comparison_note()

    print("\n[Demo complete]\n")


if __name__ == "__main__":
    main()
