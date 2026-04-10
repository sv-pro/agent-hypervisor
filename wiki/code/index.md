# Code Documentation Index

**Source root:** `src/`

This section maps the Python codebase to the [Four-Layer Architecture](../concepts/architecture.md). Every package and significant module has its own page synthesizing purpose, public API, and security invariants.

## Package Map

| Package | Wiki Page | Architecture Layer | Status |
|---|---|---|---|
| `src/core` | [core](core.md) | Cross-cutting reference impl | Canonical |
| `src/agent_hypervisor` | [agent_hypervisor](agent_hypervisor.md) | Top-level public API | Canonical |
| `src/agent_hypervisor/runtime` | [runtime](runtime.md) | Layer 3 — Execution Governance | Canonical |
| `src/agent_hypervisor/compiler` | [compiler](compiler.md) | Layer 1 — Base Ontology | Canonical |
| `src/agent_hypervisor/authoring` | [authoring](authoring.md) | Layer 2 — Dynamic Ontology | Supported |
| `src/agent_hypervisor/hypervisor` | [hypervisor](hypervisor.md) | PoC Gateway | Supported |
| `src/agent_hypervisor/control_plane` | [control_plane](control_plane.md) | World Authoring Control Plane | Supported |
| `src/agent_hypervisor/economic` | [economic](economic.md) | Economic Constraints | Supported |
| `src/agent_hypervisor/program_layer` | [program_layer](program_layer.md) | Optional Execution Abstraction | Supported |

## Module Deep-Dives

These modules own critical security invariants and warrant individual pages.

| Module | Wiki Page | Key Component |
|---|---|---|
| `runtime/ir.py` | [IR & IRBuilder](modules/ir.md) | Sealed execution intent; construction-time enforcement |
| `runtime/taint.py` | [Taint Engine](modules/taint.md) | Monotonic taint propagation |
| `runtime/compile.py` | [Compile Phase](modules/compile.md) | World Manifest → CompiledPolicy |
| `runtime/channel.py` | [Channel & Source](modules/channel.md) | Sealed trust derivation |
| `runtime/proxy.py` | [SafeMCPProxy](modules/proxy.md) | In-path MCP enforcement |
| `runtime/executor.py` | [Executor](modules/executor.md) | Subprocess transport & boundary |
| `hypervisor/firewall.py` | [ProvenanceFirewall](modules/firewall.md) | Provenance-aware tool firewall |
| `hypervisor/mcp_gateway/` | [AH MCP Gateway](modules/mcp_gateway.md) | JSON-RPC 2.0 MCP gateway; manifest-driven tool visibility; 4-stage enforcement; control-plane bridge |
| `core/hypervisor.py` | [Core Hypervisor](modules/core_hypervisor.md) | Reference manifest resolver |

## Architectural Patterns

The codebase applies several recurring security patterns. See individual module pages for instances.

| Pattern | Description | Key Modules |
|---|---|---|
| **Sealing** | Module-private sentinel prevents external construction | ir.py, channel.py, compile.py |
| **Immutability** | `__setattr__` raises after construction | IntentIR, Source, Channel, CompiledPolicy |
| **Monotonic Lattice** | Taint join; once TAINTED cannot decrease | taint.py, models.py |
| **Construction-Time Checking** | All constraints verified before IR can exist | ir.py → IRBuilder.build() |
| **Subprocess Boundary** | Main process holds zero handlers | executor.py, worker.py |
| **Fail-Closed Defaults** | Unknown → deny / UNTRUSTED / cost=∞ | channel.py, compile.py, economic/ |
| **O(1) Lookup** | Frozensets for capability/action-space tests | compile.py CompiledPolicy |
