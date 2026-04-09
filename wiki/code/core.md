# Package: `core`

**Source:** [`src/core/`](../../src/core/) — [`hypervisor.py`](../../src/core/hypervisor.py), [`__init__.py`](../../src/core/__init__.py)

`src/core` is the **portable, dependency-free reference implementation** of the Agent Hypervisor security philosophy. It is the mathematical brain of the system — it evaluates whether an action violates the [World Manifest](../concepts/world-manifest.md), without any capacity to actually execute it.

See [Codebase Structure](../concepts/codebase-analysis.md) for the full `src/core` vs `src/agent_hypervisor` comparison.

## Public API (`__init__.py`)

| Symbol | Type | Description |
|---|---|---|
| `Hypervisor` | class | Public interface: virtualize input, evaluate actions, extend manifest |
| `WorldManifest` | class | Formal specification of agent's universe (loaded from YAML) |
| `ManifestResolver` | class | Deterministic resolution engine |
| `Decision` | Enum | `ALLOW`, `DENY`, `ASK` |
| `ExecutionMode` | Enum | `WORKFLOW`, `INTERACTIVE`, `BACKGROUND` |
| `TrustLevel` | Enum | `TRUSTED`, `UNTRUSTED`, `DERIVED`, `TAINTED` |
| `ProvenanceRecord` | dataclass | Full lineage of a data object |
| `SemanticEvent` | dataclass | Structured input representation (never raw text) |

## Key Classes in `core/hypervisor.py`

### `TrustLevel`
Four-value enum: `TRUSTED`, `UNTRUSTED`, `DERIVED`, `TAINTED`. Trust is a property of an *input channel*, not of the content. The `WorldManifest` defines trust level per source.

### `Decision`
Resolution verdict: `ALLOW`, `DENY`, or `ASK`. Same manifest + same input always produces the same verdict (deterministic).

### `ExecutionMode`
Controls resolution behavior when no explicit rule matches:
- `WORKFLOW` — defining the world; strict mode
- `INTERACTIVE` — user present; may ask instead of deny
- `BACKGROUND` — user absent; strict deny on unknowns

### `ProvenanceRecord`
Full lineage of a data object. Fields: `source`, `trust_level`, `session_id`, `tainted`, `transformations`, `parent_ids`. Survives session boundaries — taint metadata cannot be stripped by crossing a session.

### `SemanticEvent`
The only form in which agents see inputs (never raw text). Fields: `event_id`, `source`, `raw_payload`, `sanitized_payload`, `trust_level`, `tainted`, `provenance`.

### `ProposedAction`
Structured request from agent to affect world. Fields: `action_id`, `action_type`, `parameters`, `provenance_chain`, `agent_reasoning`.

### `ResolutionResult`
Output of manifest resolution. Fields: `decision`, `rule_triggered`, `reason`, `provenance_summary`, `action`. Fully deterministic.

### `WorldManifest`
Formal specification of agent's universe. Loaded from YAML via `from_yaml()` or `from_dict()`.

Key methods:
- `resolve_trust(source)` → TrustLevel
- `get_capabilities(trust_level)` → list of capabilities
- `action_exists(action_type)` → bool
- `extend(additional_actions)` → new WorldManifest (immutable update; original unchanged)

### `ManifestResolver`
The deterministic resolution engine. Resolution order (strict, cannot be reordered):

1. **Invariant check** — physics laws that cannot be overridden
2. **Explicit deny rule** — if a deny rule matches, always deny
3. **Explicit allow rule** — if an allow rule matches, allow
4. **Capability check** — does the trust level permit this action type?
5. **Action not in manifest** → `ASK` (INTERACTIVE) or `DENY` (others)

Key method: `resolve(action, manifest, mode, effective_trust, is_tainted)` → `ResolutionResult`

### `Hypervisor` (Public Interface)
The only class external code should instantiate.

| Method | Description |
|---|---|
| `virtualize_input(raw_input, source, session_id)` | Transform raw text → SemanticEvent (sanitizes, assigns trust, computes taint) |
| `evaluate(proposed_action, manifest, mode)` | Evaluate ProposedAction against manifest → ResolutionResult |
| `extend_manifest(manifest, additional_actions)` | Add actions; returns new immutable manifest |

## Physics Laws (Invariants)

Two invariants are checked *before* any manifest rule lookup — they are absolute and cannot be overridden by any rule:

| Law | Description |
|---|---|
| `TaintContainmentLaw` | Tainted data cannot trigger actions with `external_side_effects` capability |
| `ProvenanceLaw` | `memory_write` requires provenance metadata (stops [ZombieAgent](../scenarios/zombie-agent.md) memory poisoning) |

## Input Sanitization

`Hypervisor.virtualize_input()` sanitizes before creating a `SemanticEvent`:
- Strips zero-width Unicode characters
- Removes `[[HIDDEN]]` patterns
- Flags hidden content as a taint trigger
- Assigns trust from compiled channel map; unknown sources → `UNTRUSTED`

## Design Intent

`src/core` contains no external dependencies and no platform-specific code. It is a **specification in code** — the same logic could be ported to Rust, Go, or TypeScript to operate at a lower systemic level, e.g., as a sidecar or kernel module.

## See Also

- [Codebase Structure](../concepts/codebase-analysis.md)
- [Trust, Taint, and Provenance](../concepts/trust-and-taint.md)
- [Manifest Resolution Law](../concepts/manifest-resolution.md)
- [World Manifest](../concepts/world-manifest.md)
- [Runtime package](runtime.md) — the heavyweight implementation of the same philosophy
