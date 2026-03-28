"""
Runtime — top-level assembler
==============================

Compiles the world manifest and wires together Channel, IRBuilder, and Executor.
This is the only module callers need to import for normal use.

Architecture (subprocess boundary edition):

    world_manifest.yaml
          │
          ▼
    compile_world()  ──────────────────────► CompiledPolicy (frozen, metadata only)
          │                                       │
          │              ┌────────────────────────┤
          │              │                        │
          ▼              ▼                        ▼
       Channel       IRBuilder               Executor (no handlers — subprocess only)
    (trust from    (construction-time            │
     compiled map)  constraint checks)           │ stdin/stdout
          │              │                        ▼
          ▼              ▼                   worker.py subprocess
        Source  ──►  IntentIR  ──────────►  (owns handlers, separate process)
                                                  │
                                                  ▼
                                            TaintedValue

Process boundary:
    - The main process (this file) holds NO callable handlers.
    - Executor is a transport facade: it creates an ExecutionSpec and sends it
      to worker.py via subprocess stdin/stdout.
    - worker.py runs in a separate process and owns the real handlers.
    - The main process cannot call handler functions directly.

Execution path:
    demo.py → IRBuilder → Runtime → ExecutionSpec → Executor → worker subprocess

Caller flow:
    from runtime import build_runtime
    from runtime.taint import TaintContext

    rt = build_runtime()
    channel = rt.channel("user")       # trust from compiled map
    source  = channel.source           # sealed — cannot be fabricated

    ctx1 = TaintContext.clean()
    ir1  = rt.builder.build("read_data", source, {"query": "x"}, ctx1)
    r1   = rt.sandbox.execute(ir1)     # TaintedValue — dispatches to worker

    ctx2 = TaintContext.from_outputs(r1)
    ir2  = rt.builder.build("send_email", source, {...}, ctx2)
    # ↑ raises ConstructionError if r1 was TAINTED and send_email is EXTERNAL
"""

from __future__ import annotations

import os
from typing import Any

from .compile import CompiledPolicy, compile_world
from .channel import Channel
from .ir import IRBuilder
from .executor import Executor, SimulationExecutor


def _assert_worker_registry_agrees(policy: CompiledPolicy) -> None:
    """
    Fail at startup if worker._REGISTRY diverges from the compiled action space.

    The worker's handler set and policy.action_space must be identical sets.
    A mismatch means either:
      - A handler exists in the worker for an action outside the compiled action
        space (unreachable but present — silent dead code risk).
      - An action is in the compiled action space but has no worker handler
        (IRBuilder would permit IR construction but execution would fail at the
        worker — caught here instead, before any request is processed).

    Both cases are caught at startup so the system refuses to start rather than
    discovering the drift at execution time.
    """
    from . import worker  # subprocess module — local import, never re-exported

    worker_actions = frozenset(worker._REGISTRY.keys())

    if worker_actions != policy.action_space:
        only_in_worker = sorted(worker_actions - policy.action_space)
        only_in_space  = sorted(policy.action_space - worker_actions)
        raise RuntimeError(
            "Worker registry diverges from compiled action space.\n"
            f"  Only in worker:       {only_in_worker}\n"
            f"  Only in action space: {only_in_space}\n"
            "Fix: update world_manifest.yaml and worker._REGISTRY to agree exactly."
        )


class Runtime:
    """
    Assembled runtime: compiled policy + channel factory + IR builder + executor.

    Immutable after construction. All components are derived from the same
    CompiledPolicy so trust assignments, capability matrix, and taint rules
    are consistent across channel resolution, IR construction, and execution.

    The runtime holds NO callable handlers. Execution is delegated to a
    worker subprocess via Executor.
    """

    __slots__ = ("_policy", "_builder", "_executor")

    def __init__(
        self,
        policy: CompiledPolicy,
        executor: Executor,
    ) -> None:
        object.__setattr__(self, "_policy", policy)
        object.__setattr__(self, "_builder", IRBuilder(policy))
        object.__setattr__(self, "_executor", executor)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Runtime is immutable after construction")

    def channel(self, identity: str) -> Channel:
        """
        Create a Channel for the given identity.

        Trust is resolved from the compiled policy — the caller cannot
        override or inject a trust level. Unknown identities resolve to
        UNTRUSTED (fail-secure).
        """
        return Channel(identity=identity, policy=self._policy)

    @property
    def builder(self) -> IRBuilder:
        """The IR builder. Use builder.build() to construct IntentIR."""
        return self._builder

    @property
    def sandbox(self) -> Executor:
        """The execution layer. Use sandbox.execute(ir) to run IntentIR."""
        return self._executor

    @property
    def executor(self) -> Executor:
        """The subprocess executor. Alias for sandbox."""
        return self._executor

    @property
    def policy(self) -> CompiledPolicy:
        """The compiled policy. Read-only metadata — no handlers."""
        return self._policy


def build_runtime(manifest_path: str = "world_manifest.yaml") -> Runtime:
    """
    Entry point: compile world manifest and return an assembled Runtime.

    No handlers are defined or held in the main process.
    Execution is delegated to worker.py via Executor (subprocess boundary).
    """
    if not os.path.isabs(manifest_path):
        # Default: look for manifest in the project root (parent of this package)
        manifest_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            manifest_path,
        )

    policy = compile_world(manifest_path)
    _assert_worker_registry_agrees(policy)
    executor = Executor()

    return Runtime(policy, executor)


def build_simulation_runtime(manifest_path: str = "world_manifest.yaml") -> Runtime:
    """
    Simulation entry point: compile world manifest and return a Runtime backed
    by SimulationExecutor instead of the real subprocess Executor.

    No subprocess is launched. No worker handlers run. Responses come entirely
    from the compiled simulation_bindings in the manifest.

    Worker registry agreement is NOT checked — simulation mode has no subprocess
    handler set to agree with. IRBuilder constraints (ontological, capability,
    taint, approval) are still enforced — simulation replaces transport, not guard.

    Raises NonSimulatableAction at execute() time if an action has no compiled
    simulation binding.
    """
    if not os.path.isabs(manifest_path):
        manifest_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            manifest_path,
        )

    policy = compile_world(manifest_path)
    executor = SimulationExecutor(policy)

    return Runtime(policy, executor)
