# docs/components/compiler.md — World Manifest Compiler

**Package:** `agent_hypervisor.compiler`  
**Role:** Compile observed execution → World Manifest → capability surface

---

## What this does

The compiler implements Layer 1 of the architecture: defining what actions exist in the agent's world. It takes a workflow definition (or observed trace), derives the minimal capability set, and renders it as the agent's Rendered Capability Surface.

```
Workflow definition
      ↓
 [profile]   derive minimal capability set  →  World Manifest (YAML)
      ↓
 [render]    Manifest → capability surface
      ↓
 [enforce]   ALLOW / DENY_ABSENT / DENY_POLICY
```

---

## Two denial types

| Type | Meaning |
|------|---------|
| `[ABSENT]` | Action has no representation in this manifest — does not exist |
| `[POLICY]` | Action exists but this call violates constraints (wrong params, tainted input) |

---

## Key modules

| Module | What it does |
|--------|-------------|
| `cli.py` | `awc` CLI — `run`, `compile`, `profile`, `render`, `init` |
| `enforcer.py` | ALLOW / DENY_ABSENT / DENY_POLICY decision engine |
| `manifest.py` | World Manifest YAML loader |
| `observe.py` | Execution trace recorder |
| `profile.py` | Derive minimal capability set from traces |
| `render.py` | Manifest → rendered capability surface |
| `schema.py` | Manifest YAML schema definition |
| `semantic_ir.py` | Semantic intermediate representation |
| `taint_compiler.py` | Taint rules → compiled state machine |

---

## Usage

```bash
# Run a scenario
awc run --scenario safe
awc run --scenario unsafe --compare
awc run --scenario zombie

# Compile a trace
awc compile <trace_file>

# Profile a workflow
awc profile <trace_file>

# Render a manifest
awc render <manifest_file>
```

---

## Example manifest

```yaml
workflow_id: repo-maintenance
version: "1.0"

capabilities:
  - tool: file_read
    constraints:
      paths: ["**/*.py", "**/*.md"]

  - tool: shell_exec
    constraints:
      commands: ["pytest"]

  - tool: git_push
    constraints:
      remotes: [origin]
```

`http_post`, `env_read`, and unrestricted `shell_exec` are not in the manifest — they don't exist in this agent's world.

---

*See `examples/compiler/` for runnable scenario demos.*  
*See `docs/architecture/world-manifest.md` for the manifest format spec.*
