# Code Documentation

**Source root:** `src/`

This section maps the Python codebase to the [Four-Layer Architecture](../concepts/architecture.md). It is organised into package-level pages (one per sub-package) and a [`modules/`](modules/README.md) subdirectory of deep-dives for security-critical modules.

## Packages

| Package | Page | Architecture Layer | One-line Summary |
|---|---|---|---|
| `src/core` | [core.md](core.md) | Reference implementation | Portable, dependency-free manifest resolver; mathematical brain of the system |
| `src/agent_hypervisor` | [agent_hypervisor.md](agent_hypervisor.md) | Top-level public API | Re-exports firewall models; entry point to all sub-packages |
| `src/agent_hypervisor/runtime` | [runtime.md](runtime.md) | Layer 3 — Execution Governance | IRBuilder, taint engine, Channel, Executor; enforces all constraints at construction time |
| `src/agent_hypervisor/compiler` | [compiler.md](compiler.md) | Layer 1 — Base Ontology | YAML → deterministic policy artifacts; `awc`/`ahc` CLI; semantic compiler pipeline |
| `src/agent_hypervisor/authoring` | [authoring.md](authoring.md) | Layer 2 — Dynamic Ontology | Capability DSL, named policy presets, MCP integration; design-time only |
| `src/agent_hypervisor/hypervisor` | [hypervisor.md](hypervisor.md) | PoC Gateway | FastAPI gateway, PolicyEngine, ProvenanceFirewall, approval workflow, policy tuner |
| `src/agent_hypervisor/control_plane` | [control_plane.md](control_plane.md) | World Authoring Control Plane | Session governance, action approvals, SessionOverlay, multi-scope approval system; sits beside the data plane |
| `src/agent_hypervisor/economic` | [economic.md](economic.md) | Economic Constraints | Budget enforcement at IR construction time; conservative cost estimation without LLM |
| `src/agent_hypervisor/program_layer` | [program_layer.md](program_layer.md) | Optional Execution Abstraction | Sandboxed program execution after all policy checks have passed |

## Module Deep-Dives

The [`modules/`](modules/README.md) subdirectory contains individual pages for every module that owns a critical security invariant.

| Module | Deep-Dive | Key Security Property |
|---|---|---|
| `runtime/ir.py` | [modules/ir.md](modules/ir.md) | Sealed `IntentIR`; construction IS the check |
| `runtime/taint.py` | [modules/taint.md](modules/taint.md) | Monotonic taint lattice; `TAINTED` is absorbing |
| `runtime/compile.py` | [modules/compile.md](modules/compile.md) | Immutable `CompiledPolicy`; O(1) capability check |
| `runtime/channel.py` | [modules/channel.md](modules/channel.md) | Sealed `Source`; trust from policy, not caller |
| `runtime/proxy.py` | [modules/proxy.md](modules/proxy.md) | Single MCP enforcement point; typed denial kinds |
| `runtime/executor.py` | [modules/executor.md](modules/executor.md) | Process boundary; main process never calls handlers |
| `hypervisor/firewall.py` | [modules/firewall.md](modules/firewall.md) | Structural provenance rules; sticky derivation (RULE-03) |
| `hypervisor/mcp_gateway/` | [modules/mcp_gateway.md](modules/mcp_gateway.md) | JSON-RPC 2.0 MCP gateway; manifest-driven tool visibility; 4-stage enforcement; control-plane bridge |
| `core/hypervisor.py` | [modules/core_hypervisor.md](modules/core_hypervisor.md) | Deterministic resolution; physics laws override all rules |

## Architectural Patterns

| Pattern | Description | Key Modules |
|---|---|---|
| **Sealing** | Module-private sentinel prevents external construction | ir.py, channel.py, compile.py |
| **Immutability** | `__setattr__` raises after construction | `IntentIR`, `Source`, `Channel`, `CompiledPolicy` |
| **Monotonic Lattice** | Taint join; once `TAINTED` cannot decrease | taint.py |
| **Construction-Time Checking** | All constraints verified before IR can exist | ir.py → `IRBuilder.build()` |
| **Subprocess Boundary** | Main process holds zero handlers | executor.py, worker.py |
| **Fail-Closed Defaults** | Unknown → deny / `UNTRUSTED` / cost=∞ | channel.py, compile.py, economic/ |
| **O(1) Lookup** | Frozensets for capability/action-space tests | compile.py `CompiledPolicy` |

## Execution Flow (Summary)

```
world_manifest.yaml
    ↓  compile_world()                [compiler/ + runtime/compile.py]
CompiledPolicy  (frozen, immutable)
    ↓  build_runtime()
Runtime
    ↓  Channel(identity).source      [runtime/channel.py]  → sealed Source
    ↓  IRBuilder.build(...)           [runtime/ir.py]       → IntentIR (or raises)
    ↓  Executor.execute(ir)           [runtime/executor.py] → TaintedValue
worker.py [subprocess]  ← handlers live here only
```

## See Also

- [Four-Layer Architecture](../concepts/architecture.md)
- [Trust, Taint, and Provenance](../concepts/trust-and-taint.md)
- [World Manifest](../concepts/world-manifest.md)
- [Code Documentation Index](index.md) — full package and module tables
