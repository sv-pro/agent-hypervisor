# Package: `agent_hypervisor`

**Source:** [`src/agent_hypervisor/__init__.py`](../../src/agent_hypervisor/__init__.py)

The top-level `agent_hypervisor` package is the public API surface for the full runtime framework. Its `__init__.py` re-exports the core firewall models that callers need without requiring them to reach into sub-packages.

## Public API

| Symbol | Type | Origin | Description |
|---|---|---|---|
| `ValueRef` | dataclass | `hypervisor.models` | A value with attached provenance metadata |
| `ToolCall` | dataclass | `hypervisor.models` | A proposed tool invocation (args as ValueRefs) |
| `Decision` | dataclass | `hypervisor.models` | Firewall verdict for one ToolCall |
| `ProvenanceClass` | Enum | `hypervisor.models` | Trust classification of a value's origin |
| `Role` | Enum | `hypervisor.models` | Semantic role of a value in a tool call |
| `Verdict` | Enum | `hypervisor.models` | allow / deny / ask / replan |
| `ProvenanceFirewall` | class | `hypervisor.firewall` | Provenance-aware tool execution firewall |
| `resolve_chain` | function | `hypervisor.provenance_eval` | Walk derivation DAG to collect all ancestors |
| `mixed_provenance` | function | `hypervisor.provenance_eval` | Detect blended/laundered provenance |

## Sub-Packages

| Sub-package | Page | Purpose |
|---|---|---|
| `runtime` | [runtime](runtime.md) | Execution governance kernel (Layer 3) |
| `compiler` | [compiler](compiler.md) | World Manifest compiler & CLI (Layer 1) |
| `authoring` | [authoring](authoring.md) | Capability DSL & policy presets (Layer 2) |
| `hypervisor` | [hypervisor](hypervisor.md) | PoC gateway, policy engine, provenance graph |
| `economic` | [economic](economic.md) | Budget enforcement & cost estimation |
| `program_layer` | [program_layer](program_layer.md) | Optional task compilation & workflow |

## Relationship to `src/core`

The `agent_hypervisor` package is the heavyweight body to `src/core`'s lightweight brain. See [Codebase Structure](../concepts/codebase-analysis.md) for a full comparison. In short:

- `src/core` — portable reference logic, no external dependencies, models the *physics*.
- `src/agent_hypervisor` — full Python framework that enforces those physics in running processes.

## See Also

- [Four-Layer Architecture](../concepts/architecture.md)
- [Trust, Taint, and Provenance](../concepts/trust-and-taint.md)
- [ProvenanceFirewall module](modules/firewall.md)
