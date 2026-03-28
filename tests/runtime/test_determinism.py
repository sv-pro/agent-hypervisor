"""
Determinism tests for the runtime kernel.

The kernel makes a strong promise: given the same manifest, action name,
source identity, params, and taint context, IRBuilder.build() always
produces the same decision — success or the same typed error. No
randomness, no external I/O, no state mutation on the decision path.

Tests:
  1. Same inputs → same IntentIR fields (pure function property)
  2. Policy compiled from same manifest is structurally identical
  3. Capability matrix is identical across compilations
  4. Taint join is deterministic (TAINTED absorbs CLEAN; order-independent)
  5. Unknown action always raises NonExistentAction (same type, same message)
  6. Taint violation always raises TaintViolation (same type)
  7. Constraint violation always raises ConstraintViolation (same type)
  8. Multiple Runtime instances from the same manifest agree on all decisions
"""

from __future__ import annotations

import os
import pytest

from runtime import (
    build_runtime,
    TaintContext,
    TaintState,
    TaintedValue,
    NonExistentAction,
    TaintViolation,
    ConstraintViolation,
    ConstructionError,
)

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


@pytest.fixture(scope="module")
def rt():
    return build_runtime(MANIFEST)


# ── 1. Same inputs → same IntentIR ────────────────────────────────────────────

def test_build_is_deterministic(rt):
    """
    build() with the same inputs produces structurally identical IntentIR objects.
    """
    source = rt.channel("user").source
    ctx = TaintContext.clean()

    ir_a = rt.builder.build("read_data", source, {"query": "hello"}, ctx)
    ir_b = rt.builder.build("read_data", source, {"query": "hello"}, ctx)

    assert ir_a.action.name == ir_b.action.name
    assert ir_a.action.action_type == ir_b.action.action_type
    assert ir_a.source.identity == ir_b.source.identity
    assert ir_a.source.trust_level == ir_b.source.trust_level
    assert ir_a.taint == ir_b.taint


# ── 2. Policy compiled from same manifest is structurally identical ────────────

def test_compiled_policy_is_deterministic():
    """
    Compiling the same manifest twice produces identical policy structures.
    """
    from runtime.compile import compile_world

    policy_a = compile_world(MANIFEST)
    policy_b = compile_world(MANIFEST)

    assert set(policy_a.actions.keys()) == set(policy_b.actions.keys())
    assert policy_a._capability_matrix == policy_b._capability_matrix
    assert policy_a._taint_rules == policy_b._taint_rules
    assert dict(policy_a._trust_map) == dict(policy_b._trust_map)


# ── 3. Capability matrix identical across compilations ────────────────────────

def test_capability_matrix_deterministic():
    """
    can_perform() returns the same bool for the same inputs across compilations.
    """
    from runtime.compile import compile_world
    from runtime.models import TrustLevel, ActionType

    p1 = compile_world(MANIFEST)
    p2 = compile_world(MANIFEST)

    for trust in TrustLevel:
        for action_type in ActionType:
            assert p1.can_perform(trust, action_type) == p2.can_perform(trust, action_type), (
                f"Mismatch for ({trust}, {action_type})"
            )


# ── 4. Taint join is deterministic and order-independent ──────────────────────

def test_taint_join_is_deterministic():
    """
    TaintState.join() is deterministic and commutative.
    """
    assert TaintState.CLEAN.join(TaintState.CLEAN) is TaintState.CLEAN
    assert TaintState.CLEAN.join(TaintState.TAINTED) is TaintState.TAINTED
    assert TaintState.TAINTED.join(TaintState.CLEAN) is TaintState.TAINTED
    assert TaintState.TAINTED.join(TaintState.TAINTED) is TaintState.TAINTED


def test_taint_context_from_outputs_is_deterministic():
    """
    TaintContext.from_outputs() always produces the same taint for the same inputs.
    """
    clean = TaintedValue(value=1, taint=TaintState.CLEAN)
    tainted = TaintedValue(value=2, taint=TaintState.TAINTED)

    for _ in range(10):
        assert TaintContext.from_outputs(clean).taint is TaintState.CLEAN
        assert TaintContext.from_outputs(tainted).taint is TaintState.TAINTED
        assert TaintContext.from_outputs(clean, tainted).taint is TaintState.TAINTED
        assert TaintContext.from_outputs(tainted, clean).taint is TaintState.TAINTED


# ── 5. Unknown action always raises NonExistentAction ─────────────────────────

def test_unknown_action_always_raises_nonexistent(rt):
    """
    build() for an unregistered action always raises NonExistentAction — same
    type, same message — regardless of how many times it is called.
    """
    source = rt.channel("user").source

    for _ in range(5):
        with pytest.raises(NonExistentAction, match="is not in the compiled action space"):
            rt.builder.build("ghost_action", source, {}, TaintContext.clean())


def test_nonexistent_action_is_subclass_of_construction_error(rt):
    """NonExistentAction is a ConstructionError — callers catching the base still work."""
    source = rt.channel("user").source
    with pytest.raises(ConstructionError):
        rt.builder.build("ghost_action", source, {}, TaintContext.clean())


# ── 6. Taint violation always raises TaintViolation ───────────────────────────

def test_taint_violation_always_raises_taintviolation(rt):
    """
    Tainted context + external action always raises TaintViolation — same
    type every time.
    """
    source = rt.channel("user").source
    tainted_ctx = TaintContext(TaintState.TAINTED)

    for _ in range(5):
        with pytest.raises(TaintViolation):
            rt.builder.build("post_webhook", source, {}, tainted_ctx)


def test_taintviolation_is_subclass_of_construction_error(rt):
    """TaintViolation is a ConstructionError."""
    source = rt.channel("user").source
    tainted_ctx = TaintContext(TaintState.TAINTED)
    with pytest.raises(ConstructionError):
        rt.builder.build("post_webhook", source, {}, tainted_ctx)


# ── 7. Constraint violation always raises ConstraintViolation ─────────────────

def test_constraint_violation_raises_typed_error(rt):
    """
    Untrusted source trying to perform an external action always raises
    ConstraintViolation.
    """
    # 'external' identity resolves to UNTRUSTED in the manifest
    source = rt.channel("external").source

    for _ in range(5):
        with pytest.raises(ConstraintViolation):
            rt.builder.build("send_email", source, {}, TaintContext.clean())


def test_constraintviolation_is_subclass_of_construction_error(rt):
    """ConstraintViolation is a ConstructionError."""
    source = rt.channel("external").source
    with pytest.raises(ConstructionError):
        rt.builder.build("send_email", source, {}, TaintContext.clean())


# ── 8. Multiple Runtime instances agree ───────────────────────────────────────

def test_two_runtimes_agree_on_decisions():
    """
    Two independently built Runtime instances make identical decisions for the
    same inputs. There is no shared mutable state between instances.
    """
    rt1 = build_runtime(MANIFEST)
    rt2 = build_runtime(MANIFEST)

    src1 = rt1.channel("user").source
    src2 = rt2.channel("user").source

    ctx = TaintContext.clean()

    # Both succeed for the same valid action
    ir1 = rt1.builder.build("read_data", src1, {"q": "x"}, ctx)
    ir2 = rt2.builder.build("read_data", src2, {"q": "x"}, ctx)
    assert ir1.action.name == ir2.action.name
    assert ir1.taint == ir2.taint

    # Both fail with the same type for the same invalid action
    with pytest.raises(NonExistentAction):
        rt1.builder.build("nonexistent", src1, {}, ctx)
    with pytest.raises(NonExistentAction):
        rt2.builder.build("nonexistent", src2, {}, ctx)
