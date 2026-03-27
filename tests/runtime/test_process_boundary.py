"""
Tests for the subprocess execution boundary.

Six focused properties:

  1. Unknown action fails before worker invocation (ConstructionError, worker never called)
  2. Tainted external action fails before worker invocation (ConstructionError, worker never called)
  3. Allowed internal action reaches worker and returns a result
  4. Runtime holds no callable handlers (Executor has no _handlers, no handler dict)
  5. Worker rejects unknown action names when sent directly (worker's own closed-world check)
  6. ExecutionSpec is serializable and minimal (only action_name + params)

Run: pytest tests/test_process_boundary.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from runtime import build_runtime
from runtime.executor import Executor, ExecutionSpec
from runtime.models import ConstructionError, NonExistentAction, TaintViolation, TaintState
from runtime.taint import TaintContext, TaintedValue

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")
WORKER = os.path.join(os.path.dirname(__file__), "..", "runtime", "worker.py")


@pytest.fixture(scope="module")
def rt():
    return build_runtime(MANIFEST)


# ── 1. Unknown action fails before worker invocation ─────────────────────────

def test_unknown_action_fails_before_worker(rt):
    """
    Actions not in the ontology raise ConstructionError at IRBuilder.build().
    The Executor._call_worker() is never reached.
    """
    channel = rt.channel("user")
    source = channel.source

    call_counter = {"count": 0}
    original_call_worker = Executor._call_worker

    def counting_call_worker(self, spec):
        call_counter["count"] += 1
        return original_call_worker(self, spec)

    with patch.object(Executor, "_call_worker", counting_call_worker):
        with pytest.raises(NonExistentAction, match="does not exist in the compiled policy"):
            rt.builder.build("delete_repository", source, {}, TaintContext.clean())

    assert call_counter["count"] == 0, (
        "Worker must not be invoked when action fails ontological check"
    )


# ── 2. Tainted external action fails before worker invocation ─────────────────

def test_tainted_external_fails_before_worker(rt):
    """
    Tainted data + external action raises ConstructionError at build time.
    Worker subprocess is never invoked.
    """
    channel = rt.channel("user")   # trusted — capability check passes
    source = channel.source

    tainted = TaintedValue(value={"url": "x"}, taint=TaintState.TAINTED)
    ctx = TaintContext.from_outputs(tainted)

    call_counter = {"count": 0}
    original_call_worker = Executor._call_worker

    def counting_call_worker(self, spec):
        call_counter["count"] += 1
        return original_call_worker(self, spec)

    with patch.object(Executor, "_call_worker", counting_call_worker):
        with pytest.raises(TaintViolation, match="[Tt]aint"):
            rt.builder.build("post_webhook", source, {"url": "https://x.com"}, ctx)

    assert call_counter["count"] == 0, (
        "Worker must not be invoked when action fails taint check"
    )


# ── 3. Allowed internal action reaches worker ─────────────────────────────────

def test_allowed_internal_action_reaches_worker(rt):
    """
    Trusted source, clean context, internal action → IR builds, worker executes.
    The worker subprocess is invoked and returns a real result.
    """
    channel = rt.channel("user")
    source = channel.source

    ctx = TaintContext.clean()
    ir = rt.builder.build("read_data", source, {"query": "test"}, ctx)

    result = rt.sandbox.execute(ir)  # real subprocess dispatch

    assert result.taint is TaintState.CLEAN
    assert isinstance(result.value, dict)
    assert "data" in result.value


def test_tainted_internal_action_reaches_worker(rt):
    """
    Tainted data + internal action → IR builds, worker executes, taint preserved.
    """
    channel = rt.channel("user")
    source = channel.source

    tainted_prior = TaintedValue(value={"query": "user-input"}, taint=TaintState.TAINTED)
    ctx = TaintContext.from_outputs(tainted_prior)

    ir = rt.builder.build("read_data", source, tainted_prior.value, ctx)
    result = rt.sandbox.execute(ir)

    assert result.taint is TaintState.TAINTED  # taint preserved across process boundary
    assert isinstance(result.value, dict)


# ── 4. Runtime holds no callable handlers ────────────────────────────────────

def test_runtime_holds_no_callable_handlers(rt):
    """
    The Runtime and its Executor hold no handler callables.

    - rt.sandbox is an Executor
    - Executor has no _handlers attribute
    - policy.actions["read_data"] has no callable handler
    """
    executor = rt.sandbox

    # Executor holds only a worker path string
    assert hasattr(executor, "_worker_path"), "Executor must have _worker_path"
    assert isinstance(executor._worker_path, str), "_worker_path must be a string"

    # No handler dict on the executor
    assert not hasattr(executor, "_handlers"), "Executor must not have _handlers"
    assert not hasattr(executor, "__handlers"), "Executor must not have __handlers"
    # Check name-mangled form explicitly
    assert not hasattr(executor, "_Executor__handlers"), (
        "Executor must not have name-mangled __handlers"
    )

    # CompiledAction has no callable execution surface (unchanged invariant)
    action = rt.policy.actions["read_data"]
    assert not hasattr(action, "_invoke")
    assert not hasattr(action, "_handler")
    assert not callable(action)


def test_executor_class_has_no_handlers():
    """
    A freshly constructed Executor has no handler callables of any kind.
    """
    ex = Executor(worker_path=WORKER)

    # No attributes that look like handler registries
    for attr in dir(ex):
        val = getattr(ex, attr, None)
        if isinstance(val, dict):
            # Any dict on the executor must not contain callables
            for v in val.values():
                assert not callable(v), (
                    f"Executor.{attr} contains a callable — handlers must not live here"
                )


# ── 5. Worker rejects unknown action names ────────────────────────────────────

def test_worker_rejects_unknown_action_directly():
    """
    If an unknown action name is somehow sent to the worker directly,
    the worker fails closed (returns ok=false) rather than executing anything.

    This proves the worker has its own independent closed-world registry.
    """
    payload = json.dumps({"action_name": "drop_database", "params": {}}).encode()

    proc = subprocess.run(
        [sys.executable, WORKER],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    response = json.loads(proc.stdout)
    assert response["ok"] is False
    assert "Unknown action" in response["error"]


def test_worker_rejects_missing_action_name():
    """
    Sending malformed input (no action_name) causes the worker to fail closed.
    """
    payload = json.dumps({"params": {"url": "https://evil.example.com"}}).encode()

    proc = subprocess.run(
        [sys.executable, WORKER],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    response = json.loads(proc.stdout)
    assert response["ok"] is False


def test_worker_executes_known_action_directly():
    """
    The worker correctly executes a known action when given a valid spec.
    This is an integration check: worker's own registry works end-to-end.
    """
    payload = json.dumps({"action_name": "read_data", "params": {"query": "ping"}}).encode()

    proc = subprocess.run(
        [sys.executable, WORKER],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    response = json.loads(proc.stdout)
    assert response["ok"] is True
    assert "data" in response["result"]
    assert b"[worker] executed read_data" in proc.stderr


# ── 6. ExecutionSpec is serializable and minimal ──────────────────────────────

def test_execution_spec_is_minimal():
    """
    ExecutionSpec carries only action_name and params.
    Nothing else crosses the process boundary.
    """
    spec = ExecutionSpec(action_name="read_data", params={"query": "x"})

    # Only two fields
    assert spec.action_name == "read_data"
    assert spec.params == {"query": "x"}

    # Serializable to JSON without error
    serialized = spec.to_json()
    parsed = json.loads(serialized)

    assert parsed["action_name"] == "read_data"
    assert parsed["params"] == {"query": "x"}
    # No extra keys — minimal
    assert set(parsed.keys()) == {"action_name", "params"}


def test_execution_spec_from_ir(rt):
    """
    ExecutionSpec.from_ir() extracts only the action name and params from an IntentIR.
    No policy objects, no Source, no taint context — just the essentials.
    """
    channel = rt.channel("user")
    source = channel.source
    ctx = TaintContext.clean()
    ir = rt.builder.build("read_data", source, {"query": "boundary-test"}, ctx)

    spec = ExecutionSpec.from_ir(ir)

    assert spec.action_name == "read_data"
    assert spec.params == {"query": "boundary-test"}

    # Spec contains no references to runtime objects
    assert not hasattr(spec, "source")
    assert not hasattr(spec, "taint")
    assert not hasattr(spec, "action")
    assert not hasattr(spec, "policy")


def test_execution_spec_serialization_round_trip():
    """
    ExecutionSpec serializes to JSON and the worker can parse it.
    Proves the boundary protocol is internally consistent.
    """
    spec = ExecutionSpec(action_name="summarize", params={"text": "hello world"})
    payload = spec.to_json().encode()

    proc = subprocess.run(
        [sys.executable, WORKER],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    response = json.loads(proc.stdout)
    assert response["ok"] is True
    assert "summary" in response["result"]
