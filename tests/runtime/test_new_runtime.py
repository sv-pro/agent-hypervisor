"""
Tests for the ontology runtime (runtime package).

Six focused properties:

  1. Unknown action fails at construction (ConstructionError from IRBuilder.build)
  2. CompiledAction has no _invoke() — execution boundary is closed
  3. Tainted internal action succeeds (taint does not mean everything blocked)
  4. Tainted external action fails through real taint path (ConstructionError)
  5. Taint drop by omission is a TypeError — TaintContext is required
  6. Approval-required actions raise ConstructionError (honestly deferred)

Run: pytest tests/test_new_runtime.py
"""

from __future__ import annotations

import os
import pytest

from runtime import build_runtime
from runtime.models import (
    ApprovalRequired,
    ConstructionError,
    NonExistentAction,
    TaintState,
    TaintViolation,
)
from runtime.taint import TaintContext, TaintedValue

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


@pytest.fixture(scope="module")
def rt():
    return build_runtime(MANIFEST)


# ── 1. Unknown action fails at construction ───────────────────────────────────

def test_unknown_action_fails_at_construction(rt):
    """
    Action names not in the ontology raise ConstructionError at IRBuilder.build().
    No IntentIR is produced; Executor.execute() is never called.
    The action does not exist in this world — it is impossible, not denied.
    """
    channel = rt.channel("user")
    source = channel.source
    with pytest.raises(NonExistentAction, match="does not exist in the compiled policy"):
        rt.builder.build("delete_repository", source, {}, TaintContext.clean())


# ── 2. Execution boundary is closed — CompiledAction has no _invoke() ─────────

def test_compiled_action_has_no_invoke(rt):
    """
    CompiledAction objects exposed via policy.actions carry no callable handler.

    - _invoke() does not exist on CompiledAction (AttributeError)
    - _handler does not exist on CompiledAction (AttributeError)

    The execution boundary is closed: the only path to a handler is
    Executor.execute(ir) with a validly constructed IntentIR.
    """
    action = rt.policy.actions["read_data"]

    assert not hasattr(action, "_invoke"), (
        "CompiledAction must not expose _invoke(); "
        "execution must go through Executor.execute(ir)"
    )
    assert not hasattr(action, "_handler"), (
        "CompiledAction must not expose _handler; "
        "handlers are private to the worker subprocess"
    )


def test_compiled_action_is_pure_metadata(rt):
    """
    CompiledAction objects have only metadata fields: name, action_type, approval_required.
    No callable attributes exist.
    """
    action = rt.policy.actions["read_data"]
    # Metadata fields exist
    assert action.name == "read_data"
    assert action.action_type.value == "internal"
    assert action.approval_required is False
    # No callable execution surface
    assert not callable(action)


# ── 3. Tainted internal action succeeds ──────────────────────────────────────

def test_tainted_internal_action_succeeds(rt):
    """
    Tainted data used for an INTERNAL action passes construction and executes.

    Taint rule blocks only TAINTED + EXTERNAL. Internal actions are reachable
    from tainted contexts. Taint is preserved in the output (monotonic).
    """
    channel = rt.channel("user")
    source = channel.source

    # Simulate a prior tainted result
    tainted_prior = TaintedValue(
        value={"query": "user-provided input"},
        taint=TaintState.TAINTED,
    )
    ctx = TaintContext.from_outputs(tainted_prior)

    ir = rt.builder.build("read_data", source, tainted_prior.value, ctx)
    result = rt.sandbox.execute(ir)

    assert result.taint is TaintState.TAINTED  # taint preserved, not dropped
    assert result.value is not None


# ── 4. Tainted external action fails through real taint path ──────────────────

def test_tainted_external_action_fails_at_construction(rt):
    """
    Tainted data used for an EXTERNAL action raises ConstructionError.

    The taint rule fires at IRBuilder.build() — before any execution path
    is entered. Executor.execute() is never reached.

    This proves taint is real physics: the IR cannot be formed, not just
    rejected at execution time.
    """
    channel = rt.channel("user")   # trusted — capability check passes
    source = channel.source

    tainted_prior = TaintedValue(
        value={"url": "https://external.example.com"},
        taint=TaintState.TAINTED,
    )
    ctx = TaintContext.from_outputs(tainted_prior)

    with pytest.raises(TaintViolation, match="[Tt]aint"):
        rt.builder.build("post_webhook", source, {"url": "https://x.com"}, ctx)


# ── 5. Taint drop by omission is now a TypeError ─────────────────────────────

def test_taint_context_required_not_variadic(rt):
    """
    IRBuilder.build() requires a TaintContext argument.

    Omitting it raises TypeError at the call site, not silently.
    """
    channel = rt.channel("user")
    source = channel.source

    with pytest.raises(TypeError):
        # Missing required taint_context argument
        rt.builder.build("read_data", source, {})  # type: ignore[call-arg]


def test_taint_context_from_outputs_carries_taint(rt):
    """
    TaintContext.from_outputs() correctly derives TAINTED from a TAINTED input.
    TaintContext.clean() correctly yields CLEAN.
    """
    tainted = TaintedValue(value="x", taint=TaintState.TAINTED)
    clean = TaintedValue(value="y", taint=TaintState.CLEAN)

    assert TaintContext.from_outputs(tainted).taint is TaintState.TAINTED
    assert TaintContext.from_outputs(clean).taint is TaintState.CLEAN
    assert TaintContext.from_outputs(clean, tainted).taint is TaintState.TAINTED
    assert TaintContext.clean().taint is TaintState.CLEAN


# ── 6. Approval-required actions are honestly deferred ───────────────────────

def test_approval_required_raises_construction_error(rt):
    """
    Actions with approval_required=True raise ConstructionError at build time.

    There is no ApprovalToken type yet. This is an honest dead end —
    the feature is not faked. Approval support is deferred.
    """
    channel = rt.channel("user")
    source = channel.source

    with pytest.raises(ApprovalRequired, match="approval"):
        rt.builder.build("download_report", source, {"id": "q1"}, TaintContext.clean())


# ── Bonus: clean action executes successfully ─────────────────────────────────

def test_clean_internal_action_executes(rt):
    """
    Happy path: trusted source, clean context, internal action → succeeds.
    """
    channel = rt.channel("user")
    source = channel.source

    ctx = TaintContext.clean()
    ir = rt.builder.build("read_data", source, {"query": "test"}, ctx)
    result = rt.sandbox.execute(ir)

    assert result.taint is TaintState.CLEAN
    assert isinstance(result.value, dict)
