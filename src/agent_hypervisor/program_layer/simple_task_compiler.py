"""
simple_task_compiler.py — SimpleTaskCompiler for Phase 1.

Translates a loosely-structured intent (string or dict) into an ExecutionPlan
using keyword matching and simple heuristics.  No LLM, no dynamic synthesis,
no probabilistic scoring.

Design contract:
    - Deterministic: the same intent always produces the same plan.
    - Fail-safe: unknown or ambiguous intents fall back to DirectExecutionPlan.
    - World-aware: if a compiled world (or action set) is supplied, the compiler
      only emits plans for workflows the world permits.
    - Non-expanding: the compiler cannot grant capabilities not already present
      in the world.

Intent formats accepted:
    str   — free-text description, e.g. "count the words in this text".
            Matched against keyword patterns; first match wins.
    dict  — structured intent with a "workflow" key, e.g.
            {"workflow": "count_words", "input": "hello world"}.
            Delegated directly to DeterministicTaskCompiler.
    other — treated as unknown; fallback to DirectExecutionPlan.

Supported workflows (same set as DeterministicTaskCompiler):
    count_lines, count_words, normalize_text, word_frequency

Keyword patterns:
    Each pattern is a (workflow, keyword) pair.  The compiler scans the
    lower-cased intent string for each keyword in order; the first match
    determines the workflow.  Patterns are ordered from most specific to
    least specific so "count lines" wins over "count" (which would otherwise
    match "count_words" first).

Usage::

    compiler = SimpleTaskCompiler()

    # String intent
    plan = compiler.compile("please count the words in this document")
    # → ProgramExecutionPlan(workflow="count_words", ...)

    # Dict intent (delegated to DeterministicTaskCompiler)
    plan = compiler.compile({"workflow": "count_lines", "timeout_seconds": 3.0})
    # → ProgramExecutionPlan(workflow="count_lines", ...)

    # Unknown intent → fallback
    plan = compiler.compile("send an email to alice")
    # → DirectExecutionPlan(...)

    # World-filtered: only workflows in world_actions are emitted
    plan = compiler.compile("count words", world_actions=frozenset({"count_lines"}))
    # → DirectExecutionPlan(...)   (count_words not in world_actions)
"""

from __future__ import annotations

import uuid
from typing import Any

from .execution_plan import DirectExecutionPlan, ExecutionPlan
from .task_compiler import DeterministicTaskCompiler

# ---------------------------------------------------------------------------
# Keyword → workflow mapping (ordered; first match wins)
# ---------------------------------------------------------------------------
# Patterns are tuples of (workflow_name, keyword_substring).
# Keywords are matched against the lower-cased, stripped intent string.
# Order matters: more specific patterns should come first.

_KEYWORD_PATTERNS: tuple[tuple[str, str], ...] = (
    # count_lines — must precede count_words to avoid "count" matching first
    ("count_lines",    "count_lines"),
    ("count_lines",    "count lines"),
    ("count_lines",    "count line"),
    ("count_lines",    "line_count"),
    ("count_lines",    "line count"),
    ("count_lines",    "number of lines"),
    ("count_lines",    "how many lines"),
    # word_frequency — most specific "frequency" patterns first
    ("word_frequency", "word_frequency"),
    ("word_frequency", "word frequency"),
    ("word_frequency", "word freq"),
    ("word_frequency", "most frequent"),
    ("word_frequency", "most common word"),
    ("word_frequency", "top words"),
    ("word_frequency", "word distribution"),
    ("word_frequency", "frequency"),
    # normalize_text
    ("normalize_text", "normalize_text"),
    ("normalize_text", "normalize text"),
    ("normalize_text", "normalise text"),
    ("normalize_text", "normalise"),
    ("normalize_text", "normalize"),
    ("normalize_text", "lowercase"),
    ("normalize_text", "lower case"),
    ("normalize_text", "lower-case"),
    ("normalize_text", "clean text"),
    ("normalize_text", "strip whitespace"),
    # count_words — least specific, comes last
    ("count_words",    "count_words"),
    ("count_words",    "count words"),
    ("count_words",    "count word"),
    ("count_words",    "count the words"),
    ("count_words",    "count the word"),
    ("count_words",    "word_count"),
    ("count_words",    "word count"),
    ("count_words",    "number of words"),
    ("count_words",    "how many words"),
    ("count_words",    "wordcount"),
)


class SimpleTaskCompiler:
    """
    Maps an intent (string or dict) to an ExecutionPlan.

    Accepts string intents via keyword matching and dict intents via
    DeterministicTaskCompiler.  Falls back to DirectExecutionPlan for
    anything it cannot map to a supported workflow.

    This is intentionally NOT smart.  It is a deterministic lookup table,
    not an LLM or a classifier.  Phase 2 will replace the matching strategy;
    the interface (compile → ExecutionPlan) stays stable.

    Satisfies the TaskCompiler protocol (interfaces.py).

    Args:
        extra_patterns: Additional (workflow, keyword) pairs to prepend
                        to the default patterns.  Useful for extending
                        the compiler in tests or custom deployments.
    """

    # The frozen set of workflows this compiler can produce plans for.
    # Mirrors DeterministicTaskCompiler.SUPPORTED_WORKFLOWS.
    SUPPORTED_WORKFLOWS: frozenset[str] = DeterministicTaskCompiler.SUPPORTED_WORKFLOWS

    def __init__(
        self,
        extra_patterns: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._base = DeterministicTaskCompiler()
        # Extra patterns are prepended so callers can override defaults.
        self._patterns: tuple[tuple[str, str], ...] = extra_patterns + _KEYWORD_PATTERNS

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compile(
        self,
        intent: Any,
        world: Any = None,
    ) -> ExecutionPlan:
        """
        Compile an intent into an ExecutionPlan.

        Args:
            intent: string or dict describing the task.  Unknown types
                    fall back to DirectExecutionPlan.
            world:  optional compiled world context.  Accepted shapes:
                    - None — no world constraint; all supported workflows
                      are available.
                    - frozenset[str] or set[str] — treated as the allowed
                      action set; workflows not in this set are blocked.
                    - object with an ``action_space`` attribute (frozenset)
                      — the compiler derives allowed workflows by
                      intersecting SUPPORTED_WORKFLOWS with action_space.
                    - object with ``allowed_workflows`` attribute
                      (frozenset[str]) — used directly as the allowed set.
                    Unknown world types → no filtering (treat as None).

        Returns:
            ProgramExecutionPlan on success, DirectExecutionPlan on fallback.
        """
        allowed = self._resolve_allowed_workflows(world)

        if isinstance(intent, dict):
            return self._compile_dict(intent, allowed)

        if isinstance(intent, str):
            return self._compile_string(intent, allowed)

        return self._fallback("unsupported intent type")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compile_dict(
        self,
        intent: dict,
        allowed: frozenset[str] | None,
    ) -> ExecutionPlan:
        """Handle structured dict intents."""
        workflow = intent.get("workflow")
        if not workflow or workflow not in self.SUPPORTED_WORKFLOWS:
            return self._fallback(f"workflow={workflow!r} not supported")

        if allowed is not None and workflow not in allowed:
            return self._fallback(
                f"workflow={workflow!r} not permitted by world"
            )

        try:
            return self._base.compile(intent, world=None)
        except ValueError:
            return self._fallback(f"compile error for workflow={workflow!r}")

    def _compile_string(
        self,
        intent: str,
        allowed: frozenset[str] | None,
    ) -> ExecutionPlan:
        """Handle free-text string intents via keyword matching."""
        normalised = intent.lower().strip()
        workflow = self._match_keyword(normalised)

        if workflow is None:
            return self._fallback(f"no workflow matched for intent={intent!r}")

        if allowed is not None and workflow not in allowed:
            return self._fallback(
                f"workflow={workflow!r} not permitted by world"
            )

        # Delegate plan generation to DeterministicTaskCompiler
        try:
            return self._base.compile({"workflow": workflow}, world=None)
        except ValueError:
            return self._fallback(f"compile error for workflow={workflow!r}")

    def _match_keyword(self, normalised_text: str) -> str | None:
        """
        Scan normalised_text for the first matching keyword.

        Returns the workflow name or None if no pattern matches.
        """
        for workflow, keyword in self._patterns:
            if keyword in normalised_text:
                return workflow
        return None

    def _resolve_allowed_workflows(self, world: Any) -> frozenset[str] | None:
        """
        Derive the allowed workflow set from the world argument.

        Returns None if world imposes no constraint.
        """
        if world is None:
            return None

        # frozenset or set of strings → use directly
        if isinstance(world, (frozenset, set)):
            return frozenset(world)

        # Object with allowed_workflows attribute
        if hasattr(world, "allowed_workflows"):
            aw = world.allowed_workflows
            if isinstance(aw, (frozenset, set)):
                return frozenset(aw)

        # Object with action_space attribute (CompiledPolicy-like)
        # Intersect with SUPPORTED_WORKFLOWS since action_space contains
        # manifest actions, not program workflow names.
        if hasattr(world, "action_space"):
            return frozenset(
                w for w in self.SUPPORTED_WORKFLOWS
                if w in world.action_space
            )

        # Unknown world type — no filtering
        return None

    def _fallback(self, reason: str) -> DirectExecutionPlan:  # noqa: ARG002
        return DirectExecutionPlan(
            plan_id=f"direct-simple-{uuid.uuid4().hex[:8]}"
        )
