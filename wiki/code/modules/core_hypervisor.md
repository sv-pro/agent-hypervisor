# Module: `core/hypervisor.py` — Core Reference Hypervisor

**Source:** [`src/core/hypervisor.py`](../../../src/core/hypervisor.py)

This module is the **portable, dependency-free reference implementation** of the Agent Hypervisor security philosophy. It is 420 lines of pure Python that implement the complete manifest resolution pipeline: input virtualization, invariant enforcement, taint tracking, provenance recording, and deterministic verdict computation.

No external dependencies. No platform-specific code. No LLM on the enforcement path.

See [Core package](../core.md) for the package-level overview and [Codebase Structure](../../concepts/codebase-analysis.md) for the comparison with `src/agent_hypervisor`.

## Key Classes

### `TrustLevel` (Enum)

Four trust tiers: `TRUSTED`, `UNTRUSTED`, `DERIVED`, `TAINTED`.

Trust is a property of an *input channel*, not of the content. The `WorldManifest` defines which sources map to which trust levels.

### `Decision` (Enum)

Three resolution verdicts: `ALLOW`, `DENY`, `ASK`.

Same manifest + same input → same verdict. Always.

### `ExecutionMode` (Enum)

Controls resolution behavior when no explicit rule matches:

| Mode | Description |
|---|---|
| `WORKFLOW` | Defining the world; unknown actions → DENY |
| `INTERACTIVE` | User present; unknown actions → ASK |
| `BACKGROUND` | User absent (automated); unknown actions → DENY |

### `ProvenanceRecord`

Full lineage of a data object. Survives session boundaries — taint metadata cannot be stripped by crossing a session.

**Fields:** `source`, `trust_level`, `session_id`, `tainted` (bool), `transformations` (list), `parent_ids` (list)

### `SemanticEvent`

The structured form in which inputs are presented to the agent. Raw text is *never* exposed — every input goes through `Hypervisor.virtualize_input()` first.

**Fields:** `event_id`, `source`, `raw_payload`, `sanitized_payload`, `trust_level`, `tainted`, `provenance`

### `ProposedAction`

Structured request from agent to affect world.

**Fields:** `action_id`, `action_type`, `parameters`, `provenance_chain`, `agent_reasoning`

### `ResolutionResult`

Output of `ManifestResolver.resolve()`. Fully deterministic.

**Fields:** `decision`, `rule_triggered`, `reason`, `provenance_summary`, `action`

### `WorldManifest`

Formal specification of agent's universe. Loaded from YAML or dict.

**Key Methods:**

| Method | Description |
|---|---|
| `from_yaml(path)` | Load from YAML file |
| `from_dict(d)` | Construct from dict |
| `resolve_trust(source)` | Look up trust level for a source name |
| `get_capabilities(trust_level)` | List capabilities available at this trust level |
| `action_exists(action_type)` | Check if action type is in manifest |
| `extend(additional_actions)` | Immutable update — returns new WorldManifest |

**Key Pattern:** Trust channels → capabilities → actions → explicit rules. Each layer narrows what is possible.

### `ManifestResolver`

The deterministic resolution engine. Resolution order is strict and cannot be reordered:

| Step | Check | Result |
|---|---|---|
| 1 | **Invariant check** (physics laws) | May return DENY immediately |
| 2 | **Explicit deny rule** | DENY if match |
| 3 | **Explicit allow rule** | ALLOW if match |
| 4 | **Capability check** | DENY if trust level doesn't permit action type |
| 5 | **Action not in manifest** | ASK (INTERACTIVE) or DENY (others) |

**Method: `resolve(action, manifest, mode, effective_trust, is_tainted) → ResolutionResult`**

### `Hypervisor` (Public Interface)

The only class external code should instantiate. Orchestrates virtualization and evaluation.

| Method | Signature | Description |
|---|---|---|
| `virtualize_input` | `(raw_input, source, session_id)` → `SemanticEvent` | Transform raw input into structured event |
| `evaluate` | `(proposed_action, manifest, mode)` → `ResolutionResult` | Evaluate action against manifest |
| `extend_manifest` | `(manifest, additional_actions)` → `WorldManifest` | Add actions; returns new immutable manifest |

## Physics Laws

Two invariants checked before any manifest rule lookup:

### `TaintContainmentLaw`
Tainted data cannot trigger actions with `external_side_effects` capability. Checked unconditionally — no manifest rule can override this.

### `ProvenanceLaw`
`memory_write` actions require provenance metadata. Ensures that every memory write carries the full lineage of the data being written — preventing memory poisoning attacks like [ZombieAgent](../../scenarios/zombie-agent.md).

## Input Sanitization (`virtualize_input`)

Before constructing a `SemanticEvent`:
1. Strips zero-width Unicode characters (common in prompt injection)
2. Removes `[[HIDDEN]]` patterns
3. Flags presence of hidden content → taint trigger
4. Assigns trust from manifest channel map; unknown sources → `UNTRUSTED`

**Key invariant:** Taint is monotonic. Once `TAINTED`, a value cannot become clean. `virtualize_input()` assigns taint; subsequent processing cannot remove it.

## Determinism Properties

`ManifestResolver.resolve()` is a pure function:

```
resolve(action, manifest, mode, effective_trust, is_tainted)
    → ResolutionResult
```

Same inputs → same result. Always. No randomness, no LLM, no external state.

This property makes the hypervisor:
- **Testable** — exhaustive test coverage is possible
- **Auditable** — every decision can be reproduced from inputs
- **Portable** — the logic can be implemented in any language that supports the same type system

## See Also

- [Core package](../core.md)
- [Codebase Structure](../../concepts/codebase-analysis.md)
- [Trust, Taint, and Provenance](../../concepts/trust-and-taint.md)
- [Manifest Resolution Law](../../concepts/manifest-resolution.md)
- [World Manifest](../../concepts/world-manifest.md)
- [Runtime package](../runtime.md) — heavyweight implementation of the same philosophy
