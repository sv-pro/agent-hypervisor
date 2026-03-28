"""
Tests for the ManifestProvenance boundary patch.

Three focused properties:

  1. Manifest hash is present on CompiledPolicy and matches the sha256 of the
     actual manifest bytes — provenance is self-verifying.

  2. build_runtime() fails at startup when worker._REGISTRY and
     CompiledPolicy.actions disagree — divergence is caught before any request.

  3. build_runtime() succeeds when the two sets agree exactly — the assertion
     does not fire on a correctly-configured world.

Run: pytest tests/runtime/test_compiled_world_provenance.py
"""

from __future__ import annotations

import hashlib
import os
import textwrap
from unittest.mock import patch

import pytest

from runtime import build_runtime
from runtime.compile import ManifestProvenance, compile_world

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


# ── 1. Manifest hash is present and correct ───────────────────────────────────

def test_provenance_is_present_on_compiled_policy():
    """
    CompiledPolicy carries a ManifestProvenance after compilation.
    The provenance object is accessible via policy.provenance.
    """
    policy = compile_world(MANIFEST)
    assert isinstance(policy.provenance, ManifestProvenance)


def test_manifest_hash_matches_file_bytes():
    """
    policy.provenance.manifest_hash equals the sha256 of the manifest file bytes.

    This is the core self-verification property: the compiled artifact can prove
    which manifest it was produced from without re-reading the file at runtime.
    """
    with open(MANIFEST, "rb") as f:
        raw_bytes = f.read()
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()

    policy = compile_world(MANIFEST)

    assert policy.provenance.manifest_hash == expected_hash


def test_workflow_id_read_from_manifest_metadata():
    """
    policy.provenance.workflow_id is read from metadata.workflow_id in the manifest.
    The test manifest carries workflow_id: agent-hypervisor-test.
    """
    policy = compile_world(MANIFEST)
    assert policy.provenance.workflow_id == "agent-hypervisor-test"


def test_workflow_id_defaults_to_unknown_when_metadata_absent(tmp_path):
    """
    If the manifest has no metadata section, workflow_id defaults to "unknown".
    compile_world() does not raise — it degrades gracefully.
    """
    manifest = tmp_path / "no_metadata.yaml"
    manifest.write_text(textwrap.dedent("""\
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
    assert policy.provenance.workflow_id == "unknown"


def test_compiled_at_is_iso8601_utc():
    """
    policy.provenance.compiled_at is an ISO-8601 string with UTC timezone (+00:00).
    """
    import datetime

    policy = compile_world(MANIFEST)
    compiled_at = policy.provenance.compiled_at

    # Must parse as a datetime without error
    dt = datetime.datetime.fromisoformat(compiled_at)
    assert dt.tzinfo is not None, "compiled_at must be timezone-aware"
    assert dt.utcoffset().total_seconds() == 0, "compiled_at must be UTC"


def test_provenance_is_immutable():
    """
    ManifestProvenance is a frozen dataclass — fields cannot be overwritten.
    """
    policy = compile_world(MANIFEST)
    with pytest.raises((AttributeError, TypeError)):
        policy.provenance.manifest_hash = "tampered"  # type: ignore[misc]


# ── 2. Startup fails on registry/policy divergence ───────────────────────────

def test_startup_fails_when_worker_has_extra_action():
    """
    build_runtime() raises RuntimeError at startup if worker._REGISTRY contains
    an action name not present in the compiled policy.

    The error message names the divergent entries so the developer can fix them.
    """
    from runtime import worker

    # Inject a fake handler that is NOT in the manifest
    patched_registry = {**worker._REGISTRY, "_ghost_action": lambda p: {}}

    with patch.object(worker, "_REGISTRY", patched_registry):
        with pytest.raises(RuntimeError) as exc_info:
            build_runtime(MANIFEST)

    msg = str(exc_info.value)
    assert "diverges from compiled world" in msg
    assert "_ghost_action" in msg
    assert "Only in worker" in msg


def test_startup_fails_when_policy_has_extra_action(tmp_path):
    """
    build_runtime() raises RuntimeError at startup if the compiled policy contains
    an action name not present in worker._REGISTRY.

    Scenario: manifest declares an action whose handler was never added to the worker.
    """
    manifest = tmp_path / "extra_action.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-extra-action
        actions:
          read_data:
            type: internal
          summarize:
            type: internal
          send_email:
            type: external
          download_report:
            type: internal
            approval_required: true
          post_webhook:
            type: external
          unimplemented_future_action:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal, external]
        taint_rules: []
    """))

    with pytest.raises(RuntimeError) as exc_info:
        build_runtime(str(manifest))

    msg = str(exc_info.value)
    assert "diverges from compiled world" in msg
    assert "unimplemented_future_action" in msg
    assert "Only in policy" in msg


def test_startup_error_names_both_sides_when_mutual_divergence():
    """
    When both sides diverge simultaneously, the error lists entries from each side.
    """
    from runtime import worker

    # Remove one real action, add one fake — mutual drift
    patched_registry = {
        k: v for k, v in worker._REGISTRY.items() if k != "post_webhook"
    }
    patched_registry["_phantom"] = lambda p: {}

    with patch.object(worker, "_REGISTRY", patched_registry):
        with pytest.raises(RuntimeError) as exc_info:
            build_runtime(MANIFEST)

    msg = str(exc_info.value)
    assert "Only in worker" in msg
    assert "Only in policy" in msg
    assert "_phantom" in msg
    assert "post_webhook" in msg


# ── 3. Startup succeeds when sets match ──────────────────────────────────────

def test_startup_succeeds_with_matching_registry(tmp_path):
    """
    build_runtime() does not raise when worker._REGISTRY exactly matches the
    compiled action set.

    Uses a manifest whose actions are a subset of worker._REGISTRY, with the
    worker patched to match exactly — verifies the happy path.
    """
    from runtime import worker

    # Patch registry to exactly {read_data} to match the minimal manifest below
    minimal_registry = {"read_data": worker._REGISTRY["read_data"]}
    manifest = tmp_path / "minimal.yaml"
    manifest.write_text(textwrap.dedent("""\
        metadata:
          workflow_id: test-minimal
        actions:
          read_data:
            type: internal
        trust:
          user: trusted
        capabilities:
          trusted: [internal]
        taint_rules: []
    """))

    with patch.object(worker, "_REGISTRY", minimal_registry):
        rt = build_runtime(str(manifest))  # must not raise

    assert rt is not None
    assert rt.policy.provenance.workflow_id == "test-minimal"


def test_startup_succeeds_with_real_manifest():
    """
    build_runtime() succeeds with the real world_manifest.yaml and the
    unmodified worker._REGISTRY — the production configuration is consistent.
    """
    rt = build_runtime(MANIFEST)
    assert rt is not None
    assert rt.policy.provenance.manifest_hash != ""
    assert len(rt.policy.provenance.manifest_hash) == 64  # sha256 hex


def test_provenance_carried_into_runtime():
    """
    The Runtime object exposes the compiled policy provenance.
    rt.policy.provenance is the same object produced by compile_world().
    """
    rt = build_runtime(MANIFEST)
    p = rt.policy.provenance

    assert isinstance(p, ManifestProvenance)
    assert p.workflow_id == "agent-hypervisor-test"
    assert len(p.manifest_hash) == 64
    assert p.compiled_at != ""
