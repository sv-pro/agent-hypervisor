# Program–World Compatibility (SYS-2 light)

## 1. Why this phase exists

A reviewed and accepted program is a **reusable structure** — the minimal set of steps that accomplished a task. But it is **not a reusable authority**. Worlds grant authority; programs do not carry it.

Before SYS-2 light, a reviewed program could be replayed against the World it was accepted under. After SYS-2 light, the same program can be re-checked and replayed under **any** registered World — and the World's current rules always decide.

> World = constitution
> Program = reviewed procedure
> Preview = constitutional review
> Replay = lawful execution under current constitution
>
> A reviewed program is reusable. Its authority is not.

This is the non-negotiable invariant: *historical acceptance does not override the currently active World.*

---

## 2. Active world vs selected world

SYS-2 light distinguishes three ways a World can become a replay's authority boundary. The choice is recorded on every `ReplayTrace` via `world_source`:

| `world_source` | Meaning |
|---|---|
| `active`   | Fetched from the registry's active-pointer (`.active.json`) — the ambient, globally-selected World. |
| `explicit` | Passed by the caller for this one replay only. Does not change the active pointer. |
| `default`  | No world context was provided; the default `SUPPORTED_WORKFLOWS` set was used. Useful for tests and for the legacy replay path. |

Switching the active World is explicit: `WorldRegistry.set_active(world_id, version)` validates the target first and rolls back if loading fails, so a bad switch never corrupts the existing active pointer.

---

## 3. Compatibility preview

`check_compatibility(program, world)` (and its registry-aware wrapper `preview_program_under_world(...)`) is a **pure deterministic validation pass**. It:

- walks each `CandidateStep` in `program.minimized_steps`;
- delegates per-step checking to `world_validator.validate_step` so the authority logic stays in one place;
- returns a `ProgramWorldCompatibility` carrying `compatible`, per-step `StepCompatibility` verdicts, and a `CompatibilitySummary` with denied-action counts.

Preview **does not execute**. Nothing runs. Nothing mutates. The same `(program, world)` pair always produces the same verdict — the byte-identical JSON from `to_dict()`.

---

## 4. Replay semantics

`ReplayEngine.replay_under_world(program, world, ...)` replays a program under a specific World and returns a `ReplayTrace`. The trace records:

- `replay_id`, `program_id`, `replayed_at`
- `world_id`, `world_version`, `world_source`
- the optional `preview_compatible` verdict if the caller ran a preview first
- the underlying `ProgramTrace` (per-step verdicts)
- `final_verdict` — one of:
  - `allow` — every step succeeded;
  - `deny` — the first step was denied (nothing executed);
  - `partial_failure` — some steps executed before a later deny.

The World's `allowed_actions` becomes the replay's authority boundary, regardless of which World the program was accepted against. Static world validation runs *before* execution — an incompatible step short-circuits the whole replay, so a `deny` verdict from `replay_under_world` means the runtime path was never entered.

The legacy `ReplayEngine.replay(program)` is unchanged and still returns a bare `ProgramTrace`.

---

## 5. Cross-world divergence

`compare_program_across_worlds(program_id, world_a_id, world_a_version, world_b_id, world_b_version, store, registry)` runs the compatibility check under both Worlds and returns a `ProgramWorldDiff`.

A **divergence point** is a step where one World allows the action and the other denies it. Steps that agree — allowed by both, denied by both — are not emitted. `both_compatible` is True only when the program is fully compatible under both Worlds.

Reading the diff:

```
step[1] 'normalize_text'
  world_a: denied: action not in allowed set; allowed: ['count_lines', 'count_words']
  world_b: allowed
  reason : world_strict denies 'normalize_text' (...)
```

This is the minimal comparative surface SYS-2 light needs; it is not a full comparative playground.

---

## 6. CLI walk-through

```bash
# List the bundled example worlds (active world marked with ●)
awc world list --worlds-dir src/agent_hypervisor/program_layer/worlds

# Switch the ambient active World (validates first, rolls back on failure)
awc world activate --id world_balanced --version 1.0 \
    --worlds-dir src/agent_hypervisor/program_layer/worlds

# Show the currently active World
awc world show --worlds-dir src/agent_hypervisor/program_layer/worlds

# Preview a reviewed program under a specific World (exit code 3 if incompatible)
awc program preview --id prog-sys2-demo --world world_strict --version 1.0 \
    --store ./programs --worlds-dir src/agent_hypervisor/program_layer/worlds

# Compare across two Worlds
awc program compare --id prog-sys2-demo \
    --world-a world_strict --world-a-version 1.0 \
    --world-b world_balanced --world-b-version 1.0 \
    --store ./programs --worlds-dir src/agent_hypervisor/program_layer/worlds

# Replay under a specific World (exit code 4 on deny, 5 on partial_failure).
# --world is optional — omit it to fall back to the active World.
awc program replay-under-world --id prog-sys2-demo \
    --world world_balanced --version 1.0 \
    --store ./programs --worlds-dir src/agent_hypervisor/program_layer/worlds
```

The full scripted flow is in `examples/program_world_compatibility_demo.py`.

---

## 7. Example divergence

The bundled worlds differ by a single action:

- `world_strict` allows `{count_lines, count_words}`.
- `world_balanced` allows `{count_lines, count_words, normalize_text, word_frequency}`.

A program with `count_words` + `normalize_text` is **compatible under `world_balanced`** (replay → `allow`) and **incompatible under `world_strict`** (replay → `deny`, nothing executes). Same bytes on disk, different Worlds, different verdicts — which is exactly the point.

---

## 8. Limitations (deliberate)

SYS-2 light is a focused bridge phase, not a control plane:

- World identity is a YAML file plus a set of action names. No CompiledPolicy, no schema validation beyond action membership, no provenance rules here.
- No policy editor, no UI beyond the CLI, no diff UI.
- No mutation of the existing enforcement path — `IRBuilder`, taint, executor, and proxy are untouched.
- The "latest version" fallback in `WorldRegistry.get` is lexicographic; semantic versioning is a future concern.

What SYS-2 light *does* establish: a reviewed program is re-validated against a World on every replay, the choice of World is explicit and auditable, and the current World always wins.
