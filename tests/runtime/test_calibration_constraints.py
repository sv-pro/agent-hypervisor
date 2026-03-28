"""
Tests for calibration constraints as a first-class compiled artifact.

Four focused property groups:

  1. Compiled artifact exposes calibration_constraints explicitly.
     policy.calibration_constraints is a MappingProxyType present on every
     CompiledPolicy, including when the manifest section is absent.

  2. CompiledCalibrationConstraint fields are correct, typed, and immutable.
     Each field is an explicit compiled type — no strings, no guessing.

  3. Fail-closed defaults are enforced.
     Absent entry → None → deny. Partial manifest entries → fail-closed field
     defaults. Empty adversarial_provenance_stop + deny policy = still deny.

  4. Execution behaviour is unchanged.
     Adding calibration constraints to the compiled artifact does not alter
     IRBuilder, taint propagation, or SimulationExecutor results.

Run: pytest tests/runtime/test_calibration_constraints.py
"""

from __future__ import annotations

import os
import textwrap

import pytest

from runtime import (
    build_runtime,
    build_simulation_runtime,
    CalibrationPolicy,
    TaintContext,
    TaintState,
    TaintedValue,
    NonExistentAction,
    TaintViolation,
    CompiledCalibrationConstraint,
)
from runtime.compile import compile_world
from runtime.models import ArgumentProvenance

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


# ── 1. Compiled artifact exposes calibration_constraints ──────────────────────

def test_calibration_constraints_exists_on_compiled_policy():
    """
    policy.calibration_constraints is present on the compiled artifact.
    """
    policy = compile_world(MANIFEST)
    assert hasattr(policy, "calibration_constraints")


def test_calibration_constraints_is_mapping_proxy():
    """
    policy.calibration_constraints is a MappingProxyType — immutable by construction.
    """
    from types import MappingProxyType
    policy = compile_world(MANIFEST)
    assert isinstance(policy.calibration_constraints, MappingProxyType)


def test_calibration_constraints_is_immutable():
    """
    The MappingProxyType cannot be mutated by callers.
    """
    policy = compile_world(MANIFEST)
    with pytest.raises((AttributeError, TypeError)):
        policy.calibration_constraints["injected"] = None  # type: ignore[index]


def test_calibration_constraints_slot_cannot_be_replaced():
    """
    CompiledPolicy is immutable — _calibration_constraints slot cannot be overwritten.
    """
    policy = compile_world(MANIFEST)
    with pytest.raises(AttributeError):
        policy._calibration_constraints = {}  # type: ignore[misc]


def test_calibration_constraints_non_empty_for_real_manifest():
    """
    The real manifest has a calibration_constraints section; compiled map is non-empty.
    """
    policy = compile_world(MANIFEST)
    assert len(policy.calibration_constraints) > 0


def test_calibration_constraints_contains_all_declared_actions():
    """
    Each action declared in calibration_constraints appears in the compiled map.
    """
    policy = compile_world(MANIFEST)
    for name in ("read_data", "summarize", "send_email", "download_report", "post_webhook"):
        assert name in policy.calibration_constraints, (
            f"{name!r} declared in calibration_constraints but absent from compiled map"
        )


def test_no_calibration_constraints_section_yields_empty_map(tmp_path):
    """
    A manifest with no calibration_constraints section compiles to an empty map.
    compile_world() does not raise.
    """
    manifest = tmp_path / "no_cal.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-no-cal
        actions:
          read_data:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
    """))

    policy = compile_world(str(manifest))
    assert len(policy.calibration_constraints) == 0
    assert policy.calibration_constraint_for("read_data") is None


def test_calibration_constraints_deterministic():
    """
    Two independent compile_world() calls produce identical calibration_constraints keys.
    """
    p1 = compile_world(MANIFEST)
    p2 = compile_world(MANIFEST)
    assert set(p1.calibration_constraints.keys()) == set(p2.calibration_constraints.keys())


# ── 2. CompiledCalibrationConstraint fields are correct and typed ──────────────

def test_compiled_calibration_constraint_is_correct_type():
    """
    Each value in calibration_constraints is a CompiledCalibrationConstraint.
    """
    policy = compile_world(MANIFEST)
    for name, constraint in policy.calibration_constraints.items():
        assert isinstance(constraint, CompiledCalibrationConstraint), (
            f"Expected CompiledCalibrationConstraint for {name!r}, got {type(constraint)}"
        )


def test_compiled_constraint_action_name_matches_key():
    """
    constraint.action_name matches the key in the calibration_constraints map.
    """
    policy = compile_world(MANIFEST)
    for key, constraint in policy.calibration_constraints.items():
        assert constraint.action_name == key


def test_compiled_constraint_expansion_policy_is_enum():
    """
    constraint.expansion_policy is a CalibrationPolicy enum — not a raw string.
    """
    policy = compile_world(MANIFEST)
    for constraint in policy.calibration_constraints.values():
        assert isinstance(constraint.expansion_policy, CalibrationPolicy)


def test_compiled_constraint_surrogate_preferred_is_bool():
    """
    constraint.surrogate_preferred is a bool — not a string or int.
    """
    policy = compile_world(MANIFEST)
    for constraint in policy.calibration_constraints.values():
        assert isinstance(constraint.surrogate_preferred, bool)


def test_compiled_constraint_requires_direct_need_is_bool():
    """
    constraint.requires_direct_need is a bool — not a string or int.
    """
    policy = compile_world(MANIFEST)
    for constraint in policy.calibration_constraints.values():
        assert isinstance(constraint.requires_direct_need, bool)


def test_compiled_constraint_adversarial_stop_is_frozenset():
    """
    constraint.adversarial_provenance_stop is a frozenset — immutable by construction.
    """
    policy = compile_world(MANIFEST)
    for constraint in policy.calibration_constraints.values():
        assert isinstance(constraint.adversarial_provenance_stop, frozenset)


def test_compiled_constraint_adversarial_stop_contains_enums():
    """
    Every member of adversarial_provenance_stop is an ArgumentProvenance enum.
    No raw strings pass through the compile boundary.
    """
    policy = compile_world(MANIFEST)
    for constraint in policy.calibration_constraints.values():
        for item in constraint.adversarial_provenance_stop:
            assert isinstance(item, ArgumentProvenance), (
                f"Expected ArgumentProvenance, got {type(item)!r}: {item!r}"
            )


def test_compiled_constraint_is_frozen():
    """
    CompiledCalibrationConstraint is a frozen dataclass — fields cannot be mutated.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("read_data")
    assert constraint is not None
    with pytest.raises((AttributeError, TypeError)):
        constraint.expansion_policy = CalibrationPolicy.allow  # type: ignore[misc]


# ── 3. Fail-closed defaults ────────────────────────────────────────────────────

def test_calibration_constraint_for_unknown_returns_none():
    """
    calibration_constraint_for() returns None for actions not in the compiled map.
    Absent entry must be interpreted as CalibrationPolicy.deny by calibration code.
    """
    policy = compile_world(MANIFEST)
    assert policy.calibration_constraint_for("ghost_action") is None
    assert policy.calibration_constraint_for("") is None


def test_none_constraint_is_the_fail_closed_sentinel():
    """
    None from calibration_constraint_for() is explicitly the fail-closed signal.
    Future calibration code that checks `if constraint is None: deny` is correct.

    This test documents the contract — not an implementation assertion.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("nonexistent")
    # The absence of a constraint IS the deny signal.
    assert constraint is None
    # Calibration code must not skip this check and proceed with expansion.
    effective_policy = (
        constraint.expansion_policy if constraint is not None else CalibrationPolicy.deny
    )
    assert effective_policy is CalibrationPolicy.deny


def test_partial_manifest_entry_uses_fail_closed_expansion_policy(tmp_path):
    """
    A calibration_constraints entry with no explicit expansion_policy defaults to deny.
    """
    manifest = tmp_path / "partial.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-partial
        actions:
          alpha:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
        calibration_constraints:
          alpha:
            surrogate_preferred: true
    """))

    policy = compile_world(str(manifest))
    constraint = policy.calibration_constraint_for("alpha")
    assert constraint is not None
    # No expansion_policy declared → must default to deny (fail-closed)
    assert constraint.expansion_policy is CalibrationPolicy.deny


def test_partial_manifest_entry_requires_direct_need_by_default(tmp_path):
    """
    A calibration_constraints entry with no requires_direct_need defaults to True.
    Derived-only need is insufficient unless explicitly relaxed.
    """
    manifest = tmp_path / "partial2.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-partial2
        actions:
          beta:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
        calibration_constraints:
          beta:
            expansion_policy: ask
    """))

    policy = compile_world(str(manifest))
    constraint = policy.calibration_constraint_for("beta")
    assert constraint is not None
    assert constraint.requires_direct_need is True


def test_read_data_expansion_is_deny():
    """
    read_data has expansion_policy: deny — it is a pure internal action
    and no capability expansion is warranted.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("read_data")
    assert constraint is not None
    assert constraint.expansion_policy is CalibrationPolicy.deny


def test_read_data_surrogate_preferred():
    """
    read_data marks surrogate_preferred: true — simulation covers all testing needs.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("read_data")
    assert constraint is not None
    assert constraint.surrogate_preferred is True


def test_send_email_expansion_is_ask():
    """
    send_email touches real external recipients — expansion requires human review.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("send_email")
    assert constraint is not None
    assert constraint.expansion_policy is CalibrationPolicy.ask


def test_send_email_requires_direct_need():
    """
    send_email requires direct (not derived) need for any expansion request.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("send_email")
    assert constraint is not None
    assert constraint.requires_direct_need is True


def test_send_email_adversarial_stop_blocks_external_document():
    """
    send_email: external_document in the adversarial_provenance_stop means
    any expansion request with external_document provenance is hard-stopped.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("send_email")
    assert constraint is not None
    assert ArgumentProvenance.external_document in constraint.adversarial_provenance_stop


def test_send_email_adversarial_stop_blocks_derived():
    """
    send_email: derived provenance is also a hard stop — adversarially induced
    derivation chains cannot be used to justify capability expansion.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("send_email")
    assert constraint is not None
    assert ArgumentProvenance.derived in constraint.adversarial_provenance_stop


def test_post_webhook_adversarial_stop_blocks_external_and_derived():
    """
    post_webhook: both external_document and derived are hard stops —
    the most common adversarial exfiltration vectors are covered.
    """
    policy = compile_world(MANIFEST)
    constraint = policy.calibration_constraint_for("post_webhook")
    assert constraint is not None
    assert ArgumentProvenance.external_document in constraint.adversarial_provenance_stop
    assert ArgumentProvenance.derived in constraint.adversarial_provenance_stop


# ── 4. Execution behaviour is unchanged ──────────────────────────────────────

def test_real_build_runtime_unaffected():
    """
    Adding calibration_constraints to the compiled artifact does not break build_runtime().
    """
    rt = build_runtime(MANIFEST)
    assert rt is not None
    assert "read_data" in rt.policy.action_space


def test_simulation_runtime_unaffected():
    """
    build_simulation_runtime() still works correctly after adding calibration_constraints.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    ctx = TaintContext.clean()
    ir = rt.builder.build("read_data", source, {}, ctx)
    result = rt.sandbox.execute(ir)
    assert result.value["data"] == "simulated-result"


def test_irbuilder_still_raises_for_nonexistent_action():
    """
    IRBuilder.build() still raises NonExistentAction — calibration_constraints
    field on CompiledPolicy does not affect the existence guard.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    with pytest.raises(NonExistentAction):
        rt.builder.build("ghost_action", source, {}, TaintContext.clean())


def test_taint_violation_still_raised_in_simulation():
    """
    TaintViolation is still raised at IR construction — calibration_constraints
    has no effect on taint enforcement.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    tainted = TaintedValue(value={"url": "x"}, taint=TaintState.TAINTED)
    ctx = TaintContext.from_outputs(tainted)
    with pytest.raises(TaintViolation):
        rt.builder.build("post_webhook", source, {}, ctx)


def test_calibration_constraints_do_not_affect_action_space():
    """
    action_space is derived only from the actions section.
    calibration_constraints has no effect on it.
    """
    policy = compile_world(MANIFEST)
    assert policy.action_space == frozenset(policy.actions.keys())
