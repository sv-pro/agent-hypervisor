"""
task_compiler.py — Minimal deterministic task compiler (Phase 1).

Purpose:
    Convert a structured intent dict into an ExecutionPlan.

Design constraints (from spec):
    - No LLM integration.
    - No dynamic synthesis.
    - Deterministic: same intent always produces the same plan.
    - Falls back to DirectExecutionPlan for unknown or unsupported intents.

Phase 1 scope:
    Supports four named workflows that cover the "read input, transform,
    produce structured output" pattern.  Each workflow maps to a small
    pre-written Python program that uses only the standard sandbox bindings.

Supported workflows:
    count_lines      — count newline-delimited lines and characters
    count_words      — count whitespace-delimited words and lines
    normalize_text   — lowercase + strip + collapse blank lines
    word_frequency   — top-N word frequencies (N configurable, default 10)

Usage::

    compiler = DeterministicTaskCompiler()

    plan = compiler.compile(
        intent={"workflow": "count_words"},
        world=None,   # world context not needed in Phase 1
    )
    # → ProgramExecutionPlan(language="python", ...)

    # Unsupported workflow → DirectExecutionPlan (fallback)
    plan = compiler.compile(intent={"workflow": "unknown"}, world=None)
    # → DirectExecutionPlan(...)

The compiler satisfies the TaskCompiler protocol defined in interfaces.py.
"""

from __future__ import annotations

import uuid
from typing import Any

from .execution_plan import DirectExecutionPlan, ExecutionPlan, ProgramExecutionPlan


# ---------------------------------------------------------------------------
# Standard allowed bindings for all compiled programs
# ---------------------------------------------------------------------------

# Every compiled program may use these bindings.
# They are injected by SandboxRuntime via _make_default_bindings().
_STANDARD_BINDINGS: tuple[str, ...] = (
    "read_input",
    "emit_result",
    "json_dumps",
    "json_loads",
)

# ---------------------------------------------------------------------------
# Pre-written program templates
# ---------------------------------------------------------------------------
# Programs are short, readable, and use only the standard sandbox bindings.
# They must pass _SecurityValidator in sandbox_runtime.py.

_PROGRAM_COUNT_LINES = """\
text = read_input()
lines = [ln for ln in text.splitlines()]
non_empty = [ln for ln in lines if ln.strip()]
emit_result({
    "line_count": len(lines),
    "non_empty_line_count": len(non_empty),
    "char_count": len(text),
})
"""

_PROGRAM_COUNT_WORDS = """\
text = read_input()
words = text.split()
lines = text.splitlines()
emit_result({
    "word_count": len(words),
    "line_count": len(lines),
    "char_count": len(text),
})
"""

_PROGRAM_NORMALIZE_TEXT = """\
text = read_input()
lowered = text.lower().strip()
lines = [ln.strip() for ln in lowered.splitlines() if ln.strip()]
normalized = "\\n".join(lines)
emit_result({
    "normalized": normalized,
    "line_count": len(lines),
    "char_count": len(normalized),
})
"""


def _make_word_frequency_program(top_n: int) -> str:
    """
    Generate a word-frequency program with a baked-in top_n limit.

    The limit is a literal integer in the generated source so there is no
    runtime parameter injection — the program is completely static.
    """
    return f"""\
text = read_input()
words = text.lower().split()
freq = {{}}
for w in words:
    freq[w] = freq.get(w, 0) + 1
pairs = sorted(freq.items(), key=lambda kv: -kv[1])[:{top_n}]
emit_result({{
    "top_words": [[w, c] for w, c in pairs],
    "unique_word_count": len(freq),
    "total_word_count": len(words),
}})
"""


# ---------------------------------------------------------------------------
# DeterministicTaskCompiler
# ---------------------------------------------------------------------------

class DeterministicTaskCompiler:
    """
    Minimal deterministic compiler: intent dict → ExecutionPlan.

    The compiler is stateless.  It reads from the intent dict and returns
    a frozen ExecutionPlan.  It never modifies the intent, never calls the
    World Kernel, and never re-evaluates policy.

    Intent dict keys:
        workflow          (str, required) — name of the workflow to compile
        timeout_seconds   (float, opt)    — execution time limit (default 5.0)
        top_n             (int, opt)      — for word_frequency workflow (default 10)

    If ``workflow`` is absent or not in SUPPORTED_WORKFLOWS, the compiler
    returns a DirectExecutionPlan so the caller falls back to direct adapter
    execution without raising an error.

    Implements the TaskCompiler protocol.
    """

    SUPPORTED_WORKFLOWS: frozenset[str] = frozenset({
        "count_lines",
        "count_words",
        "normalize_text",
        "word_frequency",
    })

    def compile(self, intent: Any, world: Any = None) -> ExecutionPlan:
        """
        Compile intent into an ExecutionPlan.

        Falls back to DirectExecutionPlan for unknown/unsupported workflows.
        Raises ValueError only for invalid parameter values within a known workflow
        (e.g. top_n out of range).
        """
        if not isinstance(intent, dict):
            return self._direct_fallback("non-dict intent")

        workflow = intent.get("workflow")
        if not workflow or workflow not in self.SUPPORTED_WORKFLOWS:
            return self._direct_fallback(f"workflow={workflow!r} not supported")

        timeout_seconds = float(intent.get("timeout_seconds", 5.0))
        if timeout_seconds <= 0:
            raise ValueError(
                f"timeout_seconds must be positive, got {timeout_seconds!r}"
            )

        program_source = self._generate_program(workflow, intent)
        plan_id = f"prog-{workflow}-{uuid.uuid4().hex[:8]}"

        return ProgramExecutionPlan(
            plan_id=plan_id,
            language="python",
            program_source=program_source,
            allowed_bindings=_STANDARD_BINDINGS,
            timeout_seconds=timeout_seconds,
            metadata={
                "workflow": workflow,
                "compiled_by": "DeterministicTaskCompiler",
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate_program(self, workflow: str, intent: dict) -> str:
        if workflow == "count_lines":
            return _PROGRAM_COUNT_LINES
        if workflow == "count_words":
            return _PROGRAM_COUNT_WORDS
        if workflow == "normalize_text":
            return _PROGRAM_NORMALIZE_TEXT
        if workflow == "word_frequency":
            top_n = int(intent.get("top_n", 10))
            if not 1 <= top_n <= 100:
                raise ValueError(
                    f"top_n must be between 1 and 100, got {top_n!r}"
                )
            return _make_word_frequency_program(top_n)
        # Should not reach here given SUPPORTED_WORKFLOWS check above
        raise ValueError(f"Unknown workflow: {workflow!r}")  # pragma: no cover

    def _direct_fallback(self, reason: str) -> DirectExecutionPlan:  # noqa: ARG002
        plan_id = f"direct-fallback-{uuid.uuid4().hex[:8]}"
        return DirectExecutionPlan(plan_id=plan_id)
