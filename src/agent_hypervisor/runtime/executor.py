"""
Executor
========

Subprocess transport facade. The execution layer.

The Executor holds NO handler functions. It holds only a path to the worker
script. Execution happens in a separate process; callable code is unreachable
from the main process.

ExecutionSpec is the ONLY thing sent across the boundary:
  - action_name (str)  — already validated by IRBuilder
  - params (dict)      — the parameters for the action

NOT sent:
  - handler functions
  - CompiledAction objects
  - policy objects
  - taint context
  - trust or capability metadata

By the time ExecutionSpec is created, the action has already passed all
ontological, capability, and taint checks in the main process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict

from .ir import IntentIR
from .models import NonSimulatableAction
from .taint import TaintedValue


# ── ExecutionSpec ─────────────────────────────────────────────────────────────

@dataclass
class ExecutionSpec:
    """
    Minimal serializable execution request.

    This is the only object that crosses the subprocess boundary.
    All policy evaluation is complete before this is created.
    """
    action_name: str
    params: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"action_name": self.action_name, "params": self.params})

    @classmethod
    def from_ir(cls, ir: IntentIR) -> "ExecutionSpec":
        """Construct from a validated IntentIR. Carries only what the worker needs."""
        return cls(action_name=ir.action.name, params=dict(ir.params))


# ── Executor ──────────────────────────────────────────────────────────────────

class Executor:
    """
    Subprocess transport: sends ExecutionSpec to the worker, returns TaintedValue.

    This class holds no handlers. It is a thin transport — its only job is to
    serialize the spec, launch the worker, and deserialize the response.

    The worker (worker.py) is a separate Python process. It owns the handlers.
    The main process cannot call those handlers directly.
    """

    def __init__(self, worker_path: str | None = None) -> None:
        if worker_path is None:
            worker_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "worker.py"
            )
        self._worker_path = worker_path

    def execute(self, ir: IntentIR) -> TaintedValue:
        """
        Execute a pre-validated IntentIR by dispatching to the worker subprocess.

        Creates an ExecutionSpec from the IR, sends it to the worker via stdin,
        reads the JSON response from stdout, and returns a TaintedValue.

        The taint from the IR is preserved in the output.
        """
        spec = ExecutionSpec.from_ir(ir)
        raw_result = self._call_worker(spec)
        return TaintedValue(value=raw_result, taint=ir.taint)

    def _call_worker(self, spec: ExecutionSpec) -> Any:
        """
        Launch worker subprocess, send spec, return deserialized result.

        stdout is captured (JSON response).
        stderr is inherited (worker's [worker] log lines appear in terminal).
        """
        payload = spec.to_json().encode()

        proc = subprocess.run(
            [sys.executable, self._worker_path],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=None,   # inherit — [worker] lines pass through to parent terminal
            timeout=30,
        )

        if not proc.stdout:
            raise RuntimeError(
                f"Worker produced no output for action {spec.action_name!r}"
            )

        try:
            response = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Worker returned invalid JSON for action {spec.action_name!r}: {exc}"
            ) from exc

        if not response.get("ok"):
            raise RuntimeError(
                f"Worker rejected action {spec.action_name!r}: "
                f"{response.get('error', 'unknown error')}"
            )

        return response["result"]


# ── SimulationExecutor ────────────────────────────────────────────────────────

class SimulationExecutor:
    """
    Surrogate executor: returns compiled simulation bindings instead of
    dispatching to the worker subprocess.

    Same interface as Executor (execute(ir) → TaintedValue) so Runtime can
    hold either executor without modification. No subprocess is launched.
    No handler code runs. The returned value comes entirely from compiled
    data in CompiledPolicy.simulation_bindings.

    IRBuilder constraints (ontological, capability, taint, approval) still
    apply before execute() is called — the IR must be validly constructed.
    SimulationExecutor only replaces the execution transport, not the guard.

    Raises NonSimulatableAction if the action has no compiled binding.
    """

    def __init__(self, policy: "Any") -> None:
        # "Any" here to avoid circular import; policy is CompiledPolicy.
        self._policy = policy

    def execute(self, ir: IntentIR) -> TaintedValue:
        """
        Return the compiled surrogate response for ir.action.name.

        Preserves ir.taint in the output — taint is monotonic even in simulation.
        Raises NonSimulatableAction if no binding is compiled for this action.
        """
        binding = self._policy.simulation_binding_for(ir.action.name)
        if binding is None:
            raise NonSimulatableAction(
                f"Action {ir.action.name!r} has no simulation binding in the compiled policy — "
                f"add a simulation_bindings entry to the manifest or use build_runtime() instead"
            )
        return TaintedValue(value=dict(binding.returns), taint=ir.taint)
