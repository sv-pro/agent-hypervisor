# docs/components/authoring.md — Capability DSL and Policy Presets

**Package:** `agent_hypervisor.authoring`  
**Role:** Define what the agent is allowed to do — capability DSL, validators, and named policy presets

---

## What this does

The authoring layer provides the developer-facing tools for defining a capability surface. It produces structured definitions that `agent_hypervisor.runtime` enforces and that `agent_hypervisor.compiler` can consume.

```
World Manifest  →  Rendered Capability Surface  →  Enforcement Engine
                         ↑
             agent_hypervisor.authoring
```

---

## Key modules

| Module | What it does |
|--------|-------------|
| `capabilities/models.py` | Typed DSL building blocks: `ValueSource`, `Constraint`, `CapabilityDef` |
| `capabilities/parser.py` | YAML / dict → `CapabilityRegistry` |
| `capabilities/validator.py` | Semantic validation: base tool refs, domain checks, constraint soundness |
| `worlds/base.py` | `BASE_WORLD` preset — read, list, summarize, search |
| `worlds/email_safe.py` | `EMAIL_SAFE_WORLD` preset — read + summarize, no send_email |
| `worlds/__init__.py` | `load_world(name)` registry |
| `integrations/mcp/server.py` | Thin `ProxyMCPServer` wrapper for MCP integration |
| `audit/logging.py` | One-line JSON event logger |

---

## Value sources in the DSL

| Source | Meaning |
|--------|---------|
| `literal` | Fixed at definition time |
| `actor_input` | Supplied by the agent at call time |
| `context_ref` | Resolved from a trusted context object |
| `resolver_ref` | Resolved by a named, declared resolver |

---

## Quick start

```python
from agent_hypervisor.authoring.worlds import load_world

world = load_world("email_safe")
# world.allowed_capabilities → frozenset({'read_data', 'summarize'})
```

```python
import yaml
from agent_hypervisor.authoring.capabilities.parser import parse_registry
from agent_hypervisor.authoring.capabilities.validator import validate

with open("my_capabilities.yaml") as f:
    data = yaml.safe_load(f)

registry = parse_registry(data)
validate(registry)   # raises ValidationError on semantic problems
```

---

## Example capability definition

```yaml
capabilities:
  send_report_to_security:
    base_tool: send_email
    args:
      to:
        valueFrom:
          literal:
            value: security@company.com   # recipient fixed — actor cannot change it
      body:
        valueFrom:
          actor_input: {}
        constraints:
          kind: text
          max_length: 5000
```

The actor cannot send to any other recipient — not because a rule blocks it, but because the capability does not accept `to` as an actor-supplied argument.

---

*See `examples/authoring/` for quickstart and attack demo.*  
*See `docs/concept/capability-rendering.md` for the construction vs. filtering explanation.*
