# Comparative Playground (SYS-3)

The Comparative Playground is the first **visible proof layer** of the Agent
Hypervisor.  It is not a UI polish layer.  It is a differential execution
analyzer that makes a single claim legible:

> **The same program produces different outcomes under different worlds.
> `program ≠ authority`; `world = authority`.**

Security is a property of the World, not of the agent.  SYS-3 lets you see
that in one command.

---

## What this shows

A **Scenario** binds ONE reviewed program to N worlds.  `run_scenario(...)`
does this, per world, without touching the sealed runtime:

1. **Preview** — `check_compatibility(program, world)` decides whether the
   program is admissible under the world's allowed-action set.
2. **Replay** — if preview passes, `ReplayEngine.replay_under_world(...)` runs
   the same enforcement path live execution uses and records a per-step
   verdict trace.
3. **Outcome matrix** — one `StepOutcome` row per `(step, world)`, carrying
   `stage`, `verdict`, and a deterministic `rule_kind`
   (`capability`, `schema`, `taint`, `policy`, `execution`).
4. **Divergence** — a step is divergent iff two worlds produced different
   verdicts at the same index.  `DivergenceReport.all_agree` is a single-bit
   summary for CI pipelines.

Typical run of the bundled `memory_write_test` scenario:

```
World: world_strict@1.0
  preview: incompatible
  step[0] count_words        ALLOW  (preview/capability: action present in world)
  step[1] normalize_text     DENY   (preview/capability: action not in allowed set)
  replay:  denied_at_preview

World: world_balanced@1.0
  preview: compatible
  step[0] count_words        ALLOW  (replay/execution: executed successfully)
  step[1] normalize_text     ALLOW  (replay/execution: executed successfully)
  replay:  allow

Divergence:
  step[1] normalize_text
    world_strict@1.0       DENY   action not in allowed set
    world_balanced@1.0     ALLOW  executed successfully
```

---

## Why it matters

Agent security frameworks tend to treat "what the agent can do" as a property
of the agent.  SYS-3 demonstrates the opposite by construction:

- The program is **immutable** across the run (the ReviewedProgram loaded
  once, reused for every world).
- No LLM call, no heuristic, no monitoring exists on the verdict path.  Every
  verdict is a deterministic consequence of the world's rules evaluated over
  the program's steps.
- The explanation for every outcome is a fixed rule class, not a generated
  sentence.  Re-running the same scenario with identical inputs produces a
  byte-identical result after scrubbing `run_id`/`ran_at`.

That makes the World a first-class, swappable authority surface.  You can
tighten or relax enforcement by changing the World, not the agent; and you
can prove the change is real by comparing two scenario runs.

---

## How to use

### CLI

```bash
# List the bundled scenarios.
awc scenario list

# Inspect a specific scenario as JSON.
awc scenario show memory_write_test

# Run it across all its worlds.
awc scenario run memory_write_test

# Same, but emit machine-readable ScenarioResult JSON.
awc scenario run memory_write_test --json

# Append every run to a persistent JSONL trace file.
awc scenario run memory_write_test --trace-file .ah/scenario_traces.jsonl
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0    | Scenario ran; all worlds agreed on every step. |
| 1    | Scenario not found, malformed YAML, or unknown world. |
| 6    | Scenario ran; at least one step diverged across worlds. |

### Python

```python
from pathlib import Path
from agent_hypervisor.program_layer import (
    ScenarioRegistry,
    WorldRegistry,
    run_scenario,
)

registry = WorldRegistry(
    worlds_dir=Path("src/agent_hypervisor/program_layer/worlds"),
    active_file=Path(".ah/active_world.json"),
)
scen_reg = ScenarioRegistry(
    Path("src/agent_hypervisor/program_layer/scenarios")
)
scenario = scen_reg.get("memory_write_test")

result = run_scenario(scenario, registry=registry)

print(f"divergence points: {len(result.divergence.divergence_points)}")
for wr in result.world_results:
    print(f"{wr.key}: preview={wr.preview_compatible} replay={wr.replay_verdict}")
```

A fully runnable end-to-end script lives at
[`examples/comparative_playground_demo.py`](../examples/comparative_playground_demo.py).

### Bundled scenarios

Under `src/agent_hypervisor/program_layer/scenarios/`:

| File | Program | Worlds | Narrative |
|------|---------|--------|-----------|
| `scenario_memory_write.yaml`  | `count_words` → `normalize_text` | strict, balanced | Writing a derived value "to memory" (stand-in: `normalize_text`) is denied under strict; allowed under balanced. |
| `scenario_external_call.yaml` | `count_lines` → `word_frequency` | strict, balanced | Producing a ranked external-facing output is denied under strict; allowed under balanced. |

### Authoring a scenario

A scenario YAML pins a program (inline steps **or** a `program_id` reference)
to two or more `(world_id, version)` pairs:

```yaml
scenario_id: my_scenario
name: "Short human-readable name"
description: "What this scenario demonstrates."
program_steps:
  - tool: count_words
    params: {input: "hello world"}
  - tool: normalize_text
    params: {input: "HELLO WORLD"}
worlds:
  - world_id: world_strict
    version: "1.0"
  - world_id: world_balanced
    version: "1.0"
```

Invariants enforced at load time:

- `worlds` must contain **at least two distinct** `(id, version)` pairs.
- `version` must be concrete — `"latest"` is rejected so scenario runs stay
  deterministic.
- Exactly one of `program_id` or `program_steps` must be set.

---

## Limitations

- **Narrative vs wired actions.**  The bundled scenarios describe "memory
  write" and "external call" in their `description` fields, but the program
  steps reuse the four real `SUPPORTED_WORKFLOWS`
  (`count_words`, `count_lines`, `normalize_text`, `word_frequency`) so the
  demos stay executable without adding stub tool handlers.  Narrative labels
  are documentation, not tool bindings.
- **Per-step-index comparison.**  Divergence is measured by step index, not
  by semantic step identity.  Inserting a step in one program but not another
  is out of scope — scenarios bind one program to many worlds, not many
  programs to many worlds.
- **`input` is opaque.**  `Scenario.input` is forwarded to the replay engine
  as `context` but is not schema-validated.  Callers treat it as free-form.
- **Timestamps are non-deterministic.**  `run_id` and `ran_at` differ across
  runs; use `ScenarioResult.scrub_run_metadata()` before byte-comparing two
  runs.
- **No HTTP surface yet.**  The CLI is the only user-facing entry point.
  Downstream systems consume `scenario run --json` or the append-only
  `ScenarioTraceStore`.

---

## Related

- World registry & activation — [SYS-2 light](../src/agent_hypervisor/program_layer/world_registry.py)
- Program review lifecycle — [PL-3](../src/agent_hypervisor/program_layer/review_lifecycle.py)
- Compatibility preview — [`compatibility.py`](../src/agent_hypervisor/program_layer/compatibility.py)
- Replay engine — [`replay_engine.py`](../src/agent_hypervisor/program_layer/replay_engine.py)
