# Module Deep-Dives

This directory contains individual pages for every module that owns a significant security-relevant component. Each page covers source location, key types, invariants, and security patterns.

## Contents

| Page | Source Module | Key Component | Security Pattern |
|---|---|---|---|
| [ir.md](ir.md) | `runtime/ir.py` | `IRBuilder`, `IntentIR` | Construction-time enforcement; Sealing |
| [taint.md](taint.md) | `runtime/taint.py` | `TaintedValue`, `TaintContext` | Monotonic lattice; taint propagation |
| [compile.md](compile.md) | `runtime/compile.py` | `compile_world()`, `CompiledPolicy` | Immutability; fail-closed defaults; O(1) lookup |
| [channel.md](channel.md) | `runtime/channel.py` | `Channel`, `Source` | Sealing; fail-secure trust derivation |
| [proxy.md](proxy.md) | `runtime/proxy.py` | `SafeMCPProxy` | Single enforcement point; explicit tool map |
| [executor.md](executor.md) | `runtime/executor.py` | `Executor`, `SimulationExecutor` | Subprocess boundary; handler isolation |
| [firewall.md](firewall.md) | `hypervisor/firewall.py` | `ProvenanceFirewall` | Structural provenance rules; sticky derivation |
| [core_hypervisor.md](core_hypervisor.md) | `core/hypervisor.py` | `Hypervisor`, `ManifestResolver` | Deterministic resolution; physics laws |

## Thematic Groupings

### Construction-Time Enforcement
`IRBuilder.build()` ([ir.md](ir.md)) is the single point where all constraints are checked. If it returns, the `IntentIR` is valid. If it raises, the action is impossible — not merely denied at execution time. `Channel` ([channel.md](channel.md)) and `compile_world()` ([compile.md](compile.md)) produce the sealed inputs that `IRBuilder` consumes.

### Data-Flow Integrity
`TaintContext` and `TaintedValue` ([taint.md](taint.md)) form the monotonic taint lattice. Every value that passes through execution carries its taint state; `map()` cannot launder it. This closes the prompt-injection-via-derivation attack vector.

### Boundary Enforcement
`SafeMCPProxy` ([proxy.md](proxy.md)) is the sole entry point for MCP tool calls; it orchestrates Channel → IRBuilder → Executor. The `Executor` ([executor.md](executor.md)) enforces the process boundary: main process holds policy, worker subprocess holds handlers — neither can reach the other's internals.

### Provenance-Layer Enforcement
`ProvenanceFirewall` ([firewall.md](firewall.md)) enforces five structural rules about value origins, operating alongside the declarative `PolicyEngine`. `ManifestResolver` in `core/hypervisor.py` ([core_hypervisor.md](core_hypervisor.md)) provides the portable reference implementation of the same resolution logic.

## See Also

- [Code Documentation Index](../index.md) — package-level pages and architectural patterns
- [Runtime package](../runtime.md) — context for `runtime/` modules
- [Hypervisor package](../hypervisor.md) — context for `hypervisor/firewall.py`
- [Core package](../core.md) — context for `core/hypervisor.py`
