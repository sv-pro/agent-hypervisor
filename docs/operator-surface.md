# Operator Surface (SYS-4A)

## 1. What SYS-4A Is

SYS-4A is the **lifecycle management shell** for the Agent Hypervisor.

The sealed runtime kernel is already deterministic. But determinism alone does not make a system manageable. Worlds can be swapped, programs accumulate, scenarios diverge — and without a management layer, none of that is visible or controlled.

SYS-4A turns existing artifacts into **managed operational objects**:

| Artifact | Before SYS-4A | After SYS-4A |
|----------|---------------|--------------|
| World | Can be activated, but with no history | Activation history, rollback, impact preview |
| Reviewed Program | Lives in ProgramStore, no operator view | Listed, inspected, compatibility checked against active world |
| Scenario | Can be run, trace stored | Listed with last-run status, divergence visible at a glance |

Mental model:

```
runtime         = kernel          (sealed, deterministic)
worlds/programs/scenarios = managed artifacts
operator surface = lifecycle shell
```

SYS-4A adds the shell. It does not modify the kernel.

---

## 2. What SYS-4A Manages

### Worlds

A **World** defines the action boundary for programs. When you activate a world, all subsequent replays run under its authority.

Worlds are loaded from YAML manifests in the worlds directory. The active-world pointer is stored atomically in `.active.json` inside that directory.

SYS-4A adds:
- **Activation history** — every activation is appended to `world_activation_history.jsonl`
- **Rollback** — restores the world that was active before the current one
- **Impact preview** — runs a deterministic compatibility check across all reviewed programs and scenarios before any activation

### Reviewed Programs

A **Reviewed Program** is a minimized, inspectable program artifact that has passed through the `propose → minimize → review → accept` lifecycle.

SYS-4A surfaces:
- `ProgramSummary` — status, world version at creation, compatibility with active world
- Per-step compatibility check against any world
- Minimization diff (what was removed and why)

### Scenarios

A **Scenario** pins one program to N worlds and records how those worlds agree or diverge.

SYS-4A surfaces:
- `ScenarioSummary` — worlds referenced, last run time, whether the last run diverged
- Last ScenarioResult from the trace store
- Whether the scenario references the active world

---

## 3. Activation and Rollback

### Activation

```
WorldOperatorService.activate_world(world_id, version, reason=None)
```

1. Snapshots the current active world.
2. Validates the target world exists (fails before writing if not).
3. Calls `WorldRegistry.set_active()` — atomic file replace.
4. Appends a `WorldActivationRecord` to `world_activation_history.jsonl`.
5. Logs to `operator_events.jsonl`.

The activation always records `previous_world_id` and `previous_version`, making rollback possible.

### Rollback

```
WorldOperatorService.rollback_world(reason=None)
```

1. Reads the most recent activation record.
2. Extracts `previous_world_id` / `previous_version`.
3. Calls `activate_world()` with `is_rollback=True`.
4. Records the rollback as a new activation entry (append-only — no history rewriting).

Fails clearly with `RollbackError` if no previous world is recorded.

### Activation History

```
WorldOperatorService.get_activation_history()  # → list[WorldActivationRecord]
```

Returns all records oldest-first from `world_activation_history.jsonl`.

Each record:

```json
{
  "activation_id": "a3f1b2c4d5e6f7a8",
  "world_id": "world_strict",
  "version": "1.0",
  "previous_world_id": "world_balanced",
  "previous_version": "1.0",
  "activated_at": "2026-04-17T12:00:00+00:00",
  "activated_by": "cli",
  "reason": "testing strict mode",
  "is_rollback": false
}
```

---

## 4. Impact Preview

Before activating a world, call:

```
WorldOperatorService.preview_activation_impact(world_id, version, store, scenario_registry)
```

This runs deterministic compatibility checks for every reviewed/accepted program and every scenario — **no execution occurs**.

Example output (`ActivationImpactReport`):

```json
{
  "target_world": {"world_id": "world_strict", "version": "1.0"},
  "current_world": {"world_id": "world_balanced", "version": "1.0"},
  "affected_programs": [
    {
      "program_id": "prog-abc123",
      "current_compatible": true,
      "target_compatible": true,
      "summary": "unchanged — compatible in both"
    },
    {
      "program_id": "prog-def456",
      "current_compatible": true,
      "target_compatible": false,
      "summary": "loses compatibility under target world"
    }
  ],
  "affected_scenarios": [
    {
      "scenario_id": "memory_write_test",
      "summary": "scenario references target world world_strict; outcomes may change",
      "divergence_expected": true
    }
  ],
  "totals": {
    "reviewed_programs_checked": 2,
    "scenarios_checked": 1,
    "programs_becoming_incompatible": 1
  },
  "generated_at": "2026-04-17T12:05:00+00:00"
}
```

Impact preview is **deterministic**: same program + same world = same verdict, every time.

---

## 5. CLI Reference

All operator commands live under `awc operator`.

### World commands

```bash
# List all worlds (● marks active)
awc operator worlds list [--worlds-dir DIR]

# Show active world as JSON
awc operator worlds active [--worlds-dir DIR]

# Activate a world (records history, validates before writing)
awc operator worlds activate world_strict [--version 1.0] [--reason "testing"] [--by cli]

# Roll back to the previous world
awc operator worlds rollback [--reason "reverting"]

# Show activation history
awc operator worlds history [--limit 20]

# Preview impact of activating a world (no execution, no mutation)
awc operator worlds impact world_strict [--version 1.0] [--json]
```

### Program commands

```bash
# List programs (● = compatible with active world)
awc operator programs list [--status reviewed] [--store ./programs]

# Show full program details as JSON
awc operator programs show <program_id>

# Show minimization diff
awc operator programs diff <program_id>

# Check compatibility (defaults to active world)
awc operator programs compatibility <program_id> [--world world_strict]
```

### Scenario commands

```bash
# List scenarios with last-run divergence
awc operator scenarios list [--trace-file ./data/traces.jsonl]

# Show scenario definition as JSON
awc operator scenarios show memory_write_test

# Print most recent scenario result
awc operator scenarios last-result memory_write_test --trace-file ./data/traces.jsonl
```

### Status summary

```bash
# Print active world + program/scenario counts
awc operator status
```

---

## 6. Event Log

Two append-only JSONL files are maintained:

| File | Contents |
|------|----------|
| `data/world_activation_history.jsonl` | One `WorldActivationRecord` per activation/rollback |
| `data/operator_events.jsonl` | One event per operator action (list, activate, preview, etc.) |

Both paths are configurable via `--history-file` and `--events-file` options.

Event record format:

```json
{
  "timestamp": "2026-04-17T12:00:00+00:00",
  "action": "activate_world",
  "target_type": "world",
  "target_id": "world_strict",
  "result": "ok",
  "details": {"version": "1.0", "previous_world_id": "world_balanced"}
}
```

---

## 7. Why This Matters

The runtime enforces deterministically — but only within a single invocation. Without a management layer:

- There is no record of which world was active when
- Rolling back requires manual file editing
- Impact of a world switch is invisible until after activation
- Program artifacts have no operator-visible health status

SYS-4A makes the lifecycle **visible, explicit, and reversible**.

---

## 8. What SYS-4A Intentionally Does NOT Include

The following belong to later phases:

| Feature | Phase |
|---------|-------|
| Approval queue | SYS-4B |
| Session inspector | SYS-5 |
| Kill switch | SYS-5 |
| Interactive web UI dashboard | SYS-6 |
| Attestation / cryptographic signatures | SYS-6 |
| Multi-user auth model | SYS-6 |
| Cloud control plane | SYS-7 |

SYS-4A is deliberately minimal: lifecycle visibility and safe world switching. Nothing more.
