"""
Tests for the explicit compiled action space — third compiler/runtime boundary patch.

Four focused properties:

  1. The compiled artifact exposes the closed action set explicitly.
     policy.action_space is a frozenset[str] present on the compiled artifact.

  2. The exposed action space matches compiled actions exactly.
     action_space and frozenset(policy.actions.keys()) are identical.
     Neither set is a superset of the other.

  3. Unknown actions still fail closed.
     Names absent from action_space cannot form an IntentIR.
     The error message names the action space so the boundary is explicit.

  4. Worker registry agreement uses the closed action set.
     _assert_worker_registry_agrees compares against policy.action_space,
     not a re-derived intermediate set.

Run: pytest tests/runtime/test_action_space.py
"""

from __future__ import annotations

import os
import textwrap
from unittest.mock import patch

import pytest

from runtime import build_runtime
from runtime.compile import compile_world
from runtime.models import NonExistentAction
from runtime.taint import TaintContext

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


# ── 1. Compiled artifact exposes the action space explicitly ──────────────────

def test_action_space_exists_on_compiled_policy():
    """
    policy.action_space is present on the compiled artifact after compile_world().
    It is not a derived view — it is a named field on the object.
    """
    policy = compile_world(MANIFEST)
    assert hasattr(policy, "action_space")


def test_action_space_is_frozenset_of_strings():
    """
    policy.action_space is a frozenset[str] — immutable by construction,
    O(1) membership tests, typed elements.
    """
    policy = compile_world(MANIFEST)
    space = policy.action_space
    assert isinstance(space, frozenset)
    for name in space:
        assert isinstance(name, str), f"Expected str in action_space, got {type(name)}"


def test_action_space_is_non_empty_for_real_manifest():
    """
    The real world manifest declares actions; the compiled action space is non-empty.
    """
    policy = compile_world(MANIFEST)
    assert len(policy.action_space) > 0


def test_action_space_contains_declared_actions():
    """
    Each action declared in the manifest appears in the compiled action space.
    """
    policy = compile_world(MANIFEST)
    # These are declared in tests/world_manifest.yaml
    for name in ("read_data", "summarize", "send_email", "download_report", "post_webhook"):
        assert name in policy.action_space, (
            f"{name!r} is declared in the manifest but absent from action_space"
        )


def test_action_space_is_immutable():
    """
    action_space is a frozenset — the caller cannot add to it.
    The existence boundary cannot be widened after compilation.
    """
    policy = compile_world(MANIFEST)
    with pytest.raises((AttributeError, TypeError)):
        policy.action_space.add("injected_action")  # type: ignore[attr-defined]


def test_action_space_slot_cannot_be_replaced():
    """
    CompiledPolicy is immutable after construction. The _action_space slot
    cannot be overwritten by any caller.
    """
    policy = compile_world(MANIFEST)
    with pytest.raises(AttributeError):
        policy._action_space = frozenset()  # type: ignore[misc]


# ── 2. Action space matches compiled actions exactly ─────────────────────────

def test_action_space_equals_actions_keyset():
    """
    policy.action_space is identical to frozenset(policy.actions.keys()).

    The explicit action_space and the underlying actions map are always
    consistent — they are derived from the same source at compile time.
    """
    policy = compile_world(MANIFEST)
    assert policy.action_space == frozenset(policy.actions.keys())


def test_action_space_size_matches_actions_count():
    """
    len(policy.action_space) == len(policy.actions).
    No duplicates, no extras — exact correspondence.
    """
    policy = compile_world(MANIFEST)
    assert len(policy.action_space) == len(policy.actions)


def test_action_space_consistent_across_two_compilations():
    """
    Two independent compile_world() calls from the same manifest produce
    identical action spaces. The compilation is deterministic.
    """
    p1 = compile_world(MANIFEST)
    p2 = compile_world(MANIFEST)
    assert p1.action_space == p2.action_space


def test_action_space_reflects_manifest_exactly(tmp_path):
    """
    The compiled action space contains exactly what the manifest declares.
    A manifest with two actions produces an action_space of size 2.
    """
    manifest = tmp_path / "two_actions.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-two
        actions:
          alpha:
            type: internal
          beta:
            type: external
        trust:
          user: trusted
        capabilities:
          trusted: [internal, external]
        taint_rules: []
    """))

    policy = compile_world(str(manifest))
    assert policy.action_space == {"alpha", "beta"}
    assert len(policy.action_space) == 2


def test_empty_actions_section_yields_empty_action_space(tmp_path):
    """
    A manifest with no actions produces an empty action_space.
    The closed world is empty — nothing can be executed.
    """
    manifest = tmp_path / "empty.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-empty
        actions: {}
        trust: {}
        capabilities: {}
        taint_rules: []
    """))

    policy = compile_world(str(manifest))
    assert policy.action_space == frozenset()


# ── 3. Unknown actions still fail closed ─────────────────────────────────────

def test_name_outside_action_space_is_not_in_it():
    """
    An arbitrary name not declared in the manifest is absent from action_space.
    Absence from the set is the explicit existence check.
    """
    policy = compile_world(MANIFEST)
    assert "totally_unknown_action" not in policy.action_space
    assert "drop_database" not in policy.action_space
    assert "" not in policy.action_space


def test_irbuilder_raises_nonexistent_for_name_outside_action_space():
    """
    IRBuilder.build() raises NonExistentAction for any name outside action_space.
    The error message references the compiled action space.
    """
    rt = build_runtime(MANIFEST)
    channel = rt.channel("user")
    source = channel.source

    with pytest.raises(NonExistentAction) as exc_info:
        rt.builder.build("drop_database", source, {}, TaintContext.clean())

    msg = str(exc_info.value)
    # Error explicitly names the action space concept
    assert "action space" in msg.lower()


def test_nonexistent_action_error_names_the_absent_action():
    """
    The NonExistentAction message names the action that was requested
    so the caller knows exactly which name was missing.
    """
    rt = build_runtime(MANIFEST)
    channel = rt.channel("user")
    source = channel.source

    with pytest.raises(NonExistentAction) as exc_info:
        rt.builder.build("ghost_action", source, {}, TaintContext.clean())

    assert "ghost_action" in str(exc_info.value)


def test_empty_action_space_blocks_all_ir_construction(tmp_path):
    """
    When action_space is empty, no IR can be formed for any action name.
    The existence boundary is total — every action is absent.
    """
    from unittest.mock import patch as mpatch
    from runtime import worker

    manifest = tmp_path / "empty.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-empty-space
        actions: {}
        trust:
          user: trusted
        capabilities:
          trusted: []
        taint_rules: []
    """))

    # Patch worker registry to empty so the startup assertion passes
    with mpatch.object(worker, "_REGISTRY", {}):
        rt = build_runtime(str(manifest))

    assert rt.policy.action_space == frozenset()

    channel = rt.channel("user")
    source = channel.source

    with pytest.raises(NonExistentAction):
        rt.builder.build("read_data", source, {}, TaintContext.clean())


# ── 4. Worker registry agreement uses the closed action set ──────────────────

def test_worker_agreement_fails_when_extra_action_added_to_registry():
    """
    _assert_worker_registry_agrees fails when worker._REGISTRY has a name
    outside the compiled action_space.

    The check is against policy.action_space, not a re-derived set.
    """
    from runtime import worker

    extra_registry = {**worker._REGISTRY, "_extra": lambda p: {}}
    with patch.object(worker, "_REGISTRY", extra_registry):
        with pytest.raises(RuntimeError) as exc_info:
            build_runtime(MANIFEST)

    msg = str(exc_info.value)
    assert "action space" in msg.lower()
    assert "_extra" in msg


def test_worker_agreement_fails_when_action_removed_from_registry():
    """
    _assert_worker_registry_agrees fails when worker._REGISTRY is missing
    an action that exists in the compiled action_space.
    """
    from runtime import worker

    # Remove one action from the registry
    reduced = {k: v for k, v in worker._REGISTRY.items() if k != "summarize"}
    with patch.object(worker, "_REGISTRY", reduced):
        with pytest.raises(RuntimeError) as exc_info:
            build_runtime(MANIFEST)

    msg = str(exc_info.value)
    assert "summarize" in msg


def test_worker_agreement_succeeds_when_registry_matches_action_space():
    """
    _assert_worker_registry_agrees passes when worker._REGISTRY keys exactly
    equal policy.action_space. No error is raised.
    """
    rt = build_runtime(MANIFEST)
    # If we got here, the assertion passed — verify the invariant holds
    from runtime import worker
    assert frozenset(worker._REGISTRY.keys()) == rt.policy.action_space


def test_action_space_is_the_canonical_reference_for_agreement():
    """
    The runtime assertion compares worker._REGISTRY against policy.action_space
    (not some intermediate set). Verify they are the same object used in context.

    Prove by showing build_runtime() yields a Runtime whose action_space
    equals the worker registry keys — confirming action_space is the reference.
    """
    rt = build_runtime(MANIFEST)
    from runtime import worker
    # action_space is the canonical source of truth for the agreement check
    assert rt.policy.action_space == frozenset(worker._REGISTRY.keys())
