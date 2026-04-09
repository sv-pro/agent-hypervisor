# Package: `authoring`

**Source:** [`src/agent_hypervisor/authoring/`](../../src/agent_hypervisor/authoring/)

The `authoring` package is **Layer 2 — Dynamic Ontology**. It provides the Capability DSL, named policy presets (World definitions), audit logging, and MCP integration tooling for *design-time* configuration of agent boundaries.

Design intent: the authoring layer is where humans specify *what is possible*. It does not execute anything — it produces configurations that the runtime and compiler layers then enforce.

## Public API (`__init__.py`)

The `authoring` `__init__.py` re-exports the Safe MCP Gateway. Entry point: `python -m safe_agent_runtime_pro --world email_safe`.

## Sub-packages & Modules

| Module | Key Symbols | Description |
|---|---|---|
| `capabilities/models.py` | `ValueSource`, `Constraint`, `ToolDefinition`, `CapabilityArgDefinition` | Typed models for the Capability DSL |
| `capabilities/parser.py` | `parse_registry()`, `load_yaml()` | Parse dict or YAML into a `CapabilityRegistry` |
| `capabilities/validator.py` | `validate()` | Semantic validation of a parsed CapabilityRegistry |
| `capabilities/examples.py` | example registries | Ready-made capability registry examples |
| `audit/logging.py` | audit logger | Structured audit log for design-time decisions |
| `integrations/mcp/server.py` | MCP server | MCP integration wrapper for tool registration |
| `worlds/base.py` | `BaseWorld` | Abstract base class for World definitions |
| `worlds/email_safe.py` | `EmailSafeWorld` | Built-in preset: email-safe agent policy |
| `main.py` | CLI entrypoint | `--world email_safe` gateway launcher |

## Capability DSL

Capabilities are declared using typed Python models (`capabilities/models.py`):

**Value Sources** — how an argument's value is obtained:
- `LiteralSource` — fixed value baked into the capability definition
- `ActorInputSource` — supplied by the agent at call time
- `ContextRefSource` — resolved from a context key
- `ResolverRefSource` — resolved by a named resolver function

**Constraints** — validation rules for argument values:
- `EmailConstraint` — optionally restricts to an allowed domain
- `TextConstraint` — optionally caps length
- `EnumConstraint` — restricts to a fixed set of values

**ToolDefinition** — the raw execution primitive: a name and an optional set of allowed argument names. `args=None` means no arg-level validation.

## World Presets

`worlds/email_safe.py` is the built-in example. It defines an `EmailSafeWorld` that restricts the agent to a controlled email-processing capability set — no external side-effects beyond explicitly permitted email actions, and recipient addresses must trace back to `user_declared` provenance.

Custom worlds extend `BaseWorld` and declare their capability registries. The resulting YAML can be compiled by the [compiler layer](compiler.md).

## Relationship to Other Layers

```
authoring/  [design-time — human authors capabilities]
    ↓  produces  world_manifest.yaml
compiler/   [compile-time — validates + emits artifacts]
    ↓  produces  CompiledPolicy
runtime/    [run-time — enforces deterministically]
```

## See Also

- [Compiler package](compiler.md)
- [Runtime package](runtime.md)
- [Four-Layer Architecture](../concepts/architecture.md)
- [World Manifest](../concepts/world-manifest.md)
