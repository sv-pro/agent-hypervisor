# Module: `runtime/compile.py` — Compile Phase

**Source:** [`src/agent_hypervisor/runtime/compile.py`](../../../src/agent_hypervisor/runtime/compile.py)

This module transforms a `world_manifest.yaml` into a **`CompiledPolicy`** — a frozen, immutable object that the entire runtime depends on. After `compile_world()` returns, the policy cannot be modified. All runtime enforcement operates against this frozen snapshot.

## Key Types

### `CompiledPolicy` (Immutable)

The frozen policy object produced by `compile_world()`. All fields are immutable after construction: `frozenset`, `MappingProxyType`, `tuple`. Mutating any field raises `TypeError` or `AttributeError`.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `_action_space` | `frozenset[str]` | Closed set of all registered action names |
| `_actions` | `MappingProxyType[str, CompiledAction]` | Metadata-only action map (no handlers) |
| `_capability_matrix` | `frozenset[tuple[TrustLevel, ActionType]]` | O(1) trust × action_type capability check |
| `_taint_rules` | `tuple[TaintRule, ...]` | Ordered taint propagation rules |
| `_trust_map` | `MappingProxyType[str, TrustLevel]` | Identity → TrustLevel; unknown → UNTRUSTED |
| `_provenance_rules` | `tuple[CompiledProvenanceRule, ...]` | Provenance verdict rules |
| `_simulation_bindings` | `MappingProxyType[str, CompiledSimulationBinding]` | Surrogate responses for simulation mode |
| `_calibration_constraints` | `MappingProxyType[str, CompiledCalibrationConstraint]` | Per-action capability expansion constraints |

**Key Methods:**

| Method | Signature | Description |
|---|---|---|
| `get_action` | `(name: str) → CompiledAction \| None` | Look up action metadata |
| `can_perform` | `(trust: TrustLevel, action_type: ActionType) → bool` | O(1) capability matrix test |
| `taint_rule_for` | `(taint: TaintState, action_type: ActionType) → TaintRule \| None` | Find applicable taint rule |
| `resolve_trust` | `(identity: str) → TrustLevel` | Resolve identity → TrustLevel (fail-closed: unknown → UNTRUSTED) |
| `evaluate_provenance` | `(...) → ProvenanceVerdict` | Evaluate provenance chain against rules |
| `simulation_binding_for` | `(action_name: str) → CompiledSimulationBinding \| None` | Look up simulation surrogate |

### `CompiledAction` (Sealed)

Pure metadata produced at compile time. **No handlers, no invocation capability.** Existence of a `CompiledAction` proves the action was present in the manifest at compile time.

**Sealing:** `__new__` checks for module-private `_COMPILE_GATE` token. Only `compile_world()` holds this token. External code cannot construct `CompiledAction`.

**Fields:** `name`, `action_type` (INTERNAL/EXTERNAL), `approval_required` (bool)

### `ManifestProvenance`

Compile-time provenance record for `CompiledPolicy`.

**Fields:** `workflow_id`, `manifest_hash` (SHA-256 of the manifest), `compiled_at` (ISO-8601 UTC)

Together these fields allow the runtime to prove *which manifest was compiled and when*, making the policy auditable.

### `TaintRule`

Immutable compiled taint rule. Fields: `taint` (TaintState), `action_type` (ActionType), `reason` (str).

### `CompiledProvenanceRule`

Compiled provenance rule. Matching: `tool` (`"*"` or exact name), `argument` (optional), `provenance` (optional). Verdict precedence: `deny (2) > ask (1) > allow (0)`. Fail-closed: no match → deny.

### `CompiledSimulationBinding` (Sealed)

Surrogate response for simulation mode. Fields: `action_name`, `returns` (`MappingProxyType`). Used exclusively by `SimulationExecutor`.

## `compile_world(manifest_path) → CompiledPolicy`

The single entry point. Reads the YAML manifest, validates it, and produces a frozen `CompiledPolicy`.

**Output structure (all immutable):**
```
CompiledPolicy
├── action_space      — frozenset[str]          closed set of valid action names
├── actions           — MappingProxyType         metadata-only action descriptors
├── capability_matrix — frozenset[tuple]         O(1) trust × type lookup
├── taint_rules       — tuple                    ordered taint rules
├── trust_map         — MappingProxyType         identity → TrustLevel
├── provenance_rules  — tuple                    provenance verdict rules
├── simulation_bindings — MappingProxyType       surrogate responses
└── manifest_provenance — ManifestProvenance     audit trail
```

**Determinism:** Same manifest YAML always produces the same `CompiledPolicy`. This makes compiled policies auditable and reproducible.

## Security Properties

1. **Sealed action metadata** — `CompiledAction` cannot be constructed outside `compile_world()`. Action existence in policy is unforgeable.
2. **Immutability** — All `CompiledPolicy` fields are Python immutable types. No in-place mutation is possible.
3. **O(1) capability check** — `can_perform()` is a frozenset membership test, not a linear scan. No approximation or ordering artifacts.
4. **Fail-closed trust** — `resolve_trust(unknown_identity)` → `UNTRUSTED`.
5. **Fail-closed provenance** — no matching rule → `deny`.
6. **Manifest hash** — `manifest_provenance.manifest_hash` lets the runtime verify it is operating against the expected manifest.

## Relationship to Other Modules

- **`loader.py`** (compiler package) validates the YAML before `compile_world()` reads it
- **`IRBuilder`** (`ir.py`) uses `CompiledPolicy.can_perform()`, `get_action()`, `taint_rule_for()`
- **`Channel`** (`channel.py`) uses `CompiledPolicy.resolve_trust()`
- **`Runtime`** (`runtime.py`) assembles all components from a single `CompiledPolicy`
- **`SimulationExecutor`** (`executor.py`) uses `CompiledPolicy.simulation_binding_for()`

## See Also

- [IR & IRBuilder](ir.md)
- [Channel & Source](channel.md)
- [Runtime package](../runtime.md)
- [Compiler package](../compiler.md) — the design-time compiler (YAML → artifacts)
- [World Manifest](../../concepts/world-manifest.md)
