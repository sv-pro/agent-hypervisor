"""
Tests for simulation bindings as a first-class compiled artifact.

Four focused property groups:

  1. Compiled artifact exposes simulation_bindings explicitly.
     policy.simulation_bindings is a MappingProxyType present on every
     CompiledPolicy regardless of whether the manifest has the section.

  2. Compiled bindings are correct and immutable.
     binding.returns matches the manifest, fields are sealed, the slot
     cannot be replaced on CompiledPolicy.

  3. SimulationExecutor uses compiled bindings, preserves taint, and raises
     NonSimulatableAction for unbound actions.

  4. build_simulation_runtime() succeeds without worker registry check.
     IRBuilder constraints still apply in simulation mode.
     Real build_runtime() path is unaffected.

Run: pytest tests/runtime/test_simulation_bindings.py
"""

from __future__ import annotations

import os
import textwrap

import pytest

from runtime import (
    build_runtime,
    build_simulation_runtime,
    TaintContext,
    TaintState,
    TaintedValue,
    NonSimulatableAction,
    CompiledSimulationBinding,
    NonExistentAction,
    TaintViolation,
)
from runtime.compile import compile_world

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


# ── 1. Compiled artifact exposes simulation_bindings ─────────────────────────

def test_simulation_bindings_exists_on_compiled_policy():
    """
    policy.simulation_bindings is present on the compiled artifact.
    It is not a derived view — it is a named field on the object.
    """
    policy = compile_world(MANIFEST)
    assert hasattr(policy, "simulation_bindings")


def test_simulation_bindings_is_mapping_proxy():
    """
    policy.simulation_bindings is a MappingProxyType — read-only by construction.
    """
    from types import MappingProxyType
    policy = compile_world(MANIFEST)
    assert isinstance(policy.simulation_bindings, MappingProxyType)


def test_simulation_bindings_is_immutable():
    """
    The simulation_bindings MappingProxyType cannot be mutated by callers.
    """
    policy = compile_world(MANIFEST)
    with pytest.raises((AttributeError, TypeError)):
        policy.simulation_bindings["injected"] = None  # type: ignore[index]


def test_simulation_bindings_slot_cannot_be_replaced():
    """
    CompiledPolicy is immutable after construction. The _simulation_bindings slot
    cannot be overwritten by any caller.
    """
    policy = compile_world(MANIFEST)
    with pytest.raises(AttributeError):
        policy._simulation_bindings = {}  # type: ignore[misc]


def test_simulation_bindings_non_empty_for_real_manifest():
    """
    The real world manifest has a simulation_bindings section;
    the compiled policy's simulation_bindings is non-empty.
    """
    policy = compile_world(MANIFEST)
    assert len(policy.simulation_bindings) > 0


def test_simulation_bindings_contains_all_declared_actions():
    """
    Each action declared in simulation_bindings appears in the compiled map.
    """
    policy = compile_world(MANIFEST)
    for name in ("read_data", "summarize", "send_email", "download_report", "post_webhook"):
        assert name in policy.simulation_bindings, (
            f"{name!r} declared in simulation_bindings but absent from compiled map"
        )


def test_no_simulation_bindings_section_yields_empty(tmp_path):
    """
    A manifest with no simulation_bindings section compiles to an empty map.
    compile_world() does not raise.
    """
    manifest = tmp_path / "no_sim.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-no-sim
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
    assert len(policy.simulation_bindings) == 0
    assert policy.simulation_binding_for("read_data") is None


def test_simulation_bindings_consistent_across_compilations():
    """
    Two independent compile_world() calls produce identical simulation_bindings keys.
    Compilation is deterministic.
    """
    p1 = compile_world(MANIFEST)
    p2 = compile_world(MANIFEST)
    assert set(p1.simulation_bindings.keys()) == set(p2.simulation_bindings.keys())


# ── 2. CompiledSimulationBinding fields are correct and immutable ──────────────

def test_compiled_binding_is_correct_type():
    """
    Each value in simulation_bindings is a CompiledSimulationBinding.
    """
    policy = compile_world(MANIFEST)
    for name, binding in policy.simulation_bindings.items():
        assert isinstance(binding, CompiledSimulationBinding), (
            f"Expected CompiledSimulationBinding for {name!r}, got {type(binding)}"
        )


def test_compiled_binding_action_name_matches_key():
    """
    binding.action_name matches the key in the simulation_bindings map.
    """
    policy = compile_world(MANIFEST)
    for key, binding in policy.simulation_bindings.items():
        assert binding.action_name == key, (
            f"binding.action_name={binding.action_name!r} does not match key={key!r}"
        )


def test_compiled_binding_returns_matches_manifest():
    """
    binding.returns for read_data matches what the manifest declares.
    """
    policy = compile_world(MANIFEST)
    binding = policy.simulation_binding_for("read_data")
    assert binding is not None
    assert binding.returns["data"] == "simulated-result"
    assert binding.returns["rows"] == 42


def test_compiled_binding_returns_is_immutable():
    """
    binding.returns is a MappingProxyType — callers cannot mutate the surrogate.
    """
    from types import MappingProxyType
    policy = compile_world(MANIFEST)
    binding = policy.simulation_binding_for("read_data")
    assert binding is not None
    assert isinstance(binding.returns, MappingProxyType)
    with pytest.raises((AttributeError, TypeError)):
        binding.returns["injected"] = "tampered"  # type: ignore[index]


def test_compiled_binding_fields_are_immutable():
    """
    CompiledSimulationBinding fields cannot be overwritten after construction.
    """
    policy = compile_world(MANIFEST)
    binding = policy.simulation_binding_for("read_data")
    assert binding is not None
    with pytest.raises(AttributeError):
        binding.action_name = "tampered"  # type: ignore[misc]


def test_simulation_binding_for_unknown_action_returns_none():
    """
    simulation_binding_for() returns None for a name not in the compiled bindings.
    """
    policy = compile_world(MANIFEST)
    assert policy.simulation_binding_for("totally_nonexistent") is None
    assert policy.simulation_binding_for("") is None


# ── 3. SimulationExecutor behaviour ──────────────────────────────────────────

def test_simulation_executor_returns_surrogate_value(tmp_path):
    """
    SimulationExecutor.execute(ir) returns the compiled surrogate response
    as a TaintedValue without launching any subprocess.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    ctx = TaintContext.clean()

    ir = rt.builder.build("read_data", source, {"query": "test"}, ctx)
    result = rt.sandbox.execute(ir)

    assert isinstance(result, TaintedValue)
    assert result.value["data"] == "simulated-result"
    assert result.value["rows"] == 42


def test_simulation_executor_preserves_clean_taint():
    """
    SimulationExecutor returns CLEAN taint when the IR carries CLEAN taint.
    Taint is not upgraded without a tainted input.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    ir = rt.builder.build("read_data", source, {}, TaintContext.clean())
    result = rt.sandbox.execute(ir)
    assert result.taint is TaintState.CLEAN


def test_simulation_executor_preserves_tainted_taint():
    """
    SimulationExecutor returns TAINTED taint when the IR carries TAINTED taint.
    Taint is monotonic — simulation cannot launder it.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    tainted_prior = TaintedValue(value={"x": 1}, taint=TaintState.TAINTED)
    ctx = TaintContext.from_outputs(tainted_prior)

    ir = rt.builder.build("read_data", source, {}, ctx)
    result = rt.sandbox.execute(ir)
    assert result.taint is TaintState.TAINTED


def test_simulation_executor_raises_for_unbound_action(tmp_path):
    """
    SimulationExecutor.execute() raises NonSimulatableAction when the action
    has no compiled simulation binding.

    The error names the unbound action so the developer knows what to add.
    """
    from unittest.mock import patch
    from runtime import worker, SimulationExecutor
    from runtime.compile import compile_world as cw

    manifest = tmp_path / "partial_sim.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-partial-sim
        actions:
          read_data:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
        simulation_bindings: {}
    """))

    policy = cw(str(manifest))
    sim_exec = SimulationExecutor(policy)

    # Build a valid IR (using the real IRBuilder with the compiled policy)
    from runtime.ir import IRBuilder
    builder = IRBuilder(policy)
    from runtime.channel import Channel
    source = Channel(identity="user", policy=policy).source

    ir = builder.build("read_data", source, {}, TaintContext.clean())
    with pytest.raises(NonSimulatableAction) as exc_info:
        sim_exec.execute(ir)

    assert "read_data" in str(exc_info.value)


def test_simulation_executor_error_names_unbound_action():
    """
    NonSimulatableAction error message names the action that had no binding.
    """
    from runtime import SimulationExecutor
    from runtime.compile import compile_world as cw
    from runtime.ir import IRBuilder
    from runtime.channel import Channel
    import textwrap

    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = os.path.join(tmp, "m.yaml")
        with open(manifest_path, "w") as f:
            f.write(textwrap.dedent("""\
                metadata:
                  workflow_id: test-error-msg
                actions:
                  alpha:
                    type: internal
                trust:
                  user: trusted
                capabilities:
                  trusted: [internal]
                taint_rules: []
            """))

        policy = cw(manifest_path)
        sim_exec = SimulationExecutor(policy)
        builder = IRBuilder(policy)
        source = Channel(identity="user", policy=policy).source
        ir = builder.build("alpha", source, {}, TaintContext.clean())

        with pytest.raises(NonSimulatableAction) as exc_info:
            sim_exec.execute(ir)

        assert "alpha" in str(exc_info.value)


# ── 4. build_simulation_runtime() and constraint enforcement ─────────────────

def test_build_simulation_runtime_succeeds_without_worker_check():
    """
    build_simulation_runtime() does not raise even though it skips the
    worker registry agreement check.
    """
    rt = build_simulation_runtime(MANIFEST)
    assert rt is not None
    assert rt.policy.provenance.workflow_id == "agent-hypervisor-test"


def test_build_simulation_runtime_exposes_simulation_bindings():
    """
    The Runtime returned by build_simulation_runtime() has the compiled
    simulation bindings accessible via rt.policy.simulation_bindings.
    """
    rt = build_simulation_runtime(MANIFEST)
    assert "read_data" in rt.policy.simulation_bindings
    assert "post_webhook" in rt.policy.simulation_bindings


def test_irbuilder_nonexistent_action_still_raises_in_simulation():
    """
    IRBuilder.build() raises NonExistentAction for an unknown name even in
    simulation mode. Simulation replaces transport, not the existence guard.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    with pytest.raises(NonExistentAction):
        rt.builder.build("ghost_action", source, {}, TaintContext.clean())


def test_irbuilder_taint_violation_still_raises_in_simulation():
    """
    TaintViolation is raised at IRBuilder.build() even in simulation mode.
    TAINTED + EXTERNAL is blocked before SimulationExecutor.execute() is reached.
    """
    rt = build_simulation_runtime(MANIFEST)
    source = rt.channel("user").source
    tainted_prior = TaintedValue(value={"url": "x"}, taint=TaintState.TAINTED)
    ctx = TaintContext.from_outputs(tainted_prior)

    with pytest.raises(TaintViolation):
        rt.builder.build("post_webhook", source, {}, ctx)


def test_real_build_runtime_unaffected():
    """
    build_runtime() still works correctly and uses the real Executor (not SimulationExecutor).
    Adding simulation_bindings to the manifest does not break the real runtime path.
    """
    from runtime.executor import Executor
    rt = build_runtime(MANIFEST)
    assert rt is not None
    # The executor on the real runtime is a subprocess Executor, not SimulationExecutor
    assert isinstance(rt.sandbox, Executor)


def test_simulation_bindings_do_not_affect_action_space():
    """
    The action_space (existence boundary) is derived only from the actions section.
    simulation_bindings has no effect on action_space.
    """
    policy = compile_world(MANIFEST)
    # action_space should equal the declared actions, not union with sim bindings
    assert policy.action_space == frozenset(policy.actions.keys())
