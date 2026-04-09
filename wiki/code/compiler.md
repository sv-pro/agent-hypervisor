# Package: `compiler`

**Source:** [`src/agent_hypervisor/compiler/`](../../src/agent_hypervisor/compiler/)

The `compiler` package is **Layer 1 — Base Ontology**. Its single responsibility is transforming a `world_manifest.yaml` into deterministic, immutable policy artifacts. It also provides the `awc`/`ahc` CLI tools for working with manifests.

The compiler is a *pure transformation pipeline*: YAML in, deterministic artifacts out. No I/O at runtime. No LLM on the enforcement path (LLM usage is design-time only, in `semantic_compiler.py`).

## Modules

| Module | Key Class/Function | Description |
|---|---|---|
| `schema.py` | `WorldManifest`, `CapabilityConstraint` | Schema dataclasses for world manifest declarations |
| `loader.py` | `load()` | Load and validate World Manifest YAML into a dict |
| `enforcer.py` | `evaluate()`, `Step`, `EvalResult` | Deterministic step evaluation against a compiled manifest |
| `cli.py` | `awc` / `ahc` CLI | Command-line interface: run, compile, profile, render |
| `manifest.py` | `load_manifest()`, `save_manifest()` | Load/save manifest YAML/JSON; generate human-readable summary |
| `primitives.py` | `SemanticPrimitive`, `PrimitiveKind` | Semantic primitive type definitions (ACTION_INTENT, QUERY_INTENT, COMMITMENT, REASONING_PATTERN) |
| `emitter.py` | `emit()` | Emit deterministic compiled artifacts to output dir |
| `profile.py` | capability profiler | Build policy profiles from execution traces |
| `render.py` | capability renderer | Render the capability surface of a manifest |
| `observe.py` | trace observation | Observe execution traces |
| `semantic_compiler.py` | `SemanticCompiler`, `LLMExtractor` | Design-time LLM pipeline: workflow definitions → draft Semantic Manifest YAML |
| `semantic_ir.py` | `SemanticExpression`, `NonRepresentableExpression`, `CandidateExpression` | Semantic Intermediate Representation pipeline |
| `semantic_manifest.py` | semantic manifest loader | Load and validate semantic manifest |
| `semantic_validator.py` | `SemanticValidator` | Deterministic (no LLM) validator for candidate semantic expressions |
| `taint_compiler.py` | taint rule compiler | Compile taint rules from manifest |

## Key Concepts

### Manifest → Policy Artifacts

`emitter.emit()` produces a set of deterministic JSON files from a validated manifest:

| Artifact | Description |
|---|---|
| `policy_table.json` | Tool whitelist, forbidden patterns, budget limits |
| `capability_matrix.json` | trust_level → permitted side_effect categories |
| `taint_rules.json` | Ordered taint propagation rules |
| `taint_state_machine.json` | Compiled O(1) taint state lookup |
| `escalation_table.json` | Trigger conditions → decisions |
| `provenance_schema.json` | Required/optional provenance fields |
| `action_schemas.json` | Per-action input schemas and metadata |
| `manifest_meta.json` | Manifest identity for audit/reproducibility |

All output is deterministic: **same manifest → same files, always.**

### The Semantic Compiler Pipeline (Design-Time Only)

```
workflow_definitions
    → extract_patterns()     [LLM — offline]
    → propose_primitives()   [LLM — offline]
    → generate_edge_cases()  [LLM — offline]
    → draft Semantic Manifest YAML  [for human review]
```

The LLM is injected as a `LLMExtractor` protocol. It operates entirely offline (design-time), never on the execution path.

### Semantic IR Pipeline

```
natural language
    → [SemanticMapper]          [LLM — online]
    → [SemanticValidator]       [deterministic, no LLM]
    → SemanticExpression             → flows into Intent IR
    → NonRepresentableExpression     → terminates (prompt injection caught here)
    → CapabilityRequiredExpression   → terminates (capability audit)
```

The key security property: **prompt injection produces a `NonRepresentableExpression`** because injected text has no registered primitive — it never reaches execution.

### Step Evaluation (Enforcer)

`enforcer.evaluate(step, manifest)` returns an `EvalResult` with one of:
- `ALLOW` — step is permitted
- `DENY_ABSENT` — action has no representation in manifest at all
- `DENY_POLICY` — action exists but violates a constraint (e.g., tainted input)
- `REQUIRE_APPROVAL` — action requires human approval

Two distinct denial categories matter for auditing: "never existed" vs "existed but violated a rule".

## CLI (`awc` / `ahc`)

```bash
awc run --scenario safe
awc run --scenario unsafe --compare
awc compile --manifest path/to/manifest.yaml
awc profile --trace path/to/trace.json
awc render --manifest path/to/manifest.yaml
```

## See Also

- [Four-Layer Architecture](../concepts/architecture.md)
- [World Manifest](../concepts/world-manifest.md)
- [AI Aikido](../concepts/ai-aikido.md) — how design-time LLM produces deterministic artifacts
- [Compile Phase module](modules/compile.md) — runtime compile_world() companion
