# docs/components/runtime.md — Enforcement Kernel

**Package:** `agent_hypervisor.runtime`  
**Role:** Deterministic enforcement kernel

---

## What this does

The runtime is the Layer 3 enforcement boundary. All constraint checking happens at IR construction time — not at execution time. If `build()` returns an `IntentIR`, every constraint has already passed. If it raises, nothing executes.

```
Agent / LLM
    │
    ▼
IRBuilder.build()      ← enforcement happens here
    │ success → IntentIR
    ▼
Executor.execute()     ← outcome of enforcement
    │
    ▼
TaintedValue
```

---

## Key components

| Module | What it does |
|--------|-------------|
| `runtime.py` | `build_runtime(manifest_path)` — single entry point |
| `compile.py` | `compile_world(path)` → `CompiledPolicy` (run once at startup) |
| `ir.py` | `IRBuilder.build()` — all constraints evaluated here |
| `taint.py` | `TaintContext`, `TaintedValue` — monotonic taint propagation |
| `executor.py` | `Executor.execute(ir)` — runs only validated `IntentIR` |
| `proxy.py` | `SafeMCPProxy` — in-path enforcement for MCP-style callers |
| `channel.py` | `Channel` — resolves source identity → trust level |
| `models.py` | Data models shared across the runtime |

---

## Enforcement model

Three denial types are structurally distinct:

| Exception | Meaning |
|-----------|---------|
| `NonExistentAction` | Action not in manifest — ontological absence |
| `ConstraintViolation` | Trust level insufficient for this action type |
| `TaintViolation` | Tainted context cannot flow into this action |
| `ApprovalRequired` | Action requires an approval token |

All four are subclasses of `ConstructionError`.

---

## Quick start

```python
from agent_hypervisor.runtime import build_runtime, TaintContext

rt = build_runtime("world_manifest.yaml")
channel = rt.channel("user")

ir = rt.builder.build(
    action_name="read_data",
    source=channel.source,
    params={"query": "hello"},
    taint_context=TaintContext.clean(),
)
result = rt.sandbox.execute(ir)
```

---

*See `world_manifest.yaml` for manifest format.*  
*See `docs/architecture/technical-spec.md` for the formal specification.*
