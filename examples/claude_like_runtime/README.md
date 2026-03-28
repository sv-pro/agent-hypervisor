# Claude-Like Coding Runtime Demo

> **"Advertising tools is rendering the agent's reality."**

This demo proves a single claim: the actions you render into a Compiled World
define the agent's ontological surface — what is possible, what can be conceived,
what can be done. Same model. Same task. Same repo. Different Compiled Worlds.
Different outcomes.

This is not a guardrail demo. There is no filter, no policy engine, no blocker.
Actions simply do not exist in worlds where they were not rendered.

---

## The Claim

An LLM agent's effective reality is determined by the action space it is given.
If `git_push` is not in the Compiled World's action space, the agent cannot push —
not because it is blocked, but because push does not exist in that world.

Rendered reality → rendered action space → rendered outcome.

---

## Artifact Model

Each world follows the compilation pipeline:

```
World Manifest (YAML) → compile_world() → CompiledWorld → Runtime
```

- **World Manifest** — YAML source defining `action_space` and `simulation_bindings`
- **compile_world()** — local compilation step; manifest is not re-read at runtime
- **CompiledWorld** — immutable artifact with a closed `frozenset` action space
- **Runtime** — consumes the CompiledWorld; dispatches via action space membership

---

## Three Compiled Worlds

| World             | Action Space                                          | Push Outcome                  |
|-------------------|-------------------------------------------------------|-------------------------------|
| `raw_world`       | read, write, shell, git status/commit/push            | Real push executes            |
| `rendered_world`  | read, grep, list, test (all simulation-bound)         | Push is absent from world     |
| `simulated_world` | read, grep, list, test + `git_push_simulated`         | Simulated push (sim binding)  |

### raw_world
Broad action space. No simulation bindings. All real side effects available.
The agent inhabits a world where writing, shelling, committing, and pushing
are all ontologically present and execute against real state.

### rendered_world
Restricted action space. Read-only and test-oriented. No write, no shell, no git.
All present actions are simulation-bound: execution runs against curated snapshots.
Push is not blocked — it is absent from the Compiled World's action space.

### simulated_world
Same read/test action space as `rendered_world`, plus `git_push_simulated`.
The agent traverses the complete push workflow; the side effect is captured
in the simulation layer rather than executed against the real remote.
All actions carry a simulation binding.

---

## Structure

```
examples/claude_like_runtime/
├── main.py                        # Entry point
├── runtime/
│   ├── compiled_world.py          # CompiledWorld artifact + compile_world()
│   ├── world_loader.py            # Thin re-export of compile_world()
│   ├── world_switcher.py          # Manage active Compiled World, print action space
│   └── audit.py                   # Structured event log
├── tools/
│   ├── proxy.py                   # WorldProxy: action space check + binding dispatch
│   ├── real_tools.py              # Real execution implementations
│   └── simulated_tools.py        # Simulation layer implementations
├── world/
│   ├── raw_world.yaml             # World Manifest — broad action space
│   ├── rendered_world.yaml        # World Manifest — restricted + all sim-bound
│   └── simulated_world.yaml      # World Manifest — restricted + sim push
└── scenarios/
    └── same_task_different_world.md   # Full scenario walkthrough
```

---

## Setup

```bash
# From repo root
pip install anthropic pyyaml

export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Running the Demo

```bash
cd examples/claude_like_runtime

# Run all three Compiled Worlds sequentially (recommended first run)
python main.py

# Run a single Compiled World
python main.py --world raw_world
python main.py --world rendered_world
python main.py --world simulated_world

# Preview action spaces without API calls
python main.py --dry-run
```

### Expected output structure

```
────────────────────────────────────────────────────────
  COMPILED WORLD : raw_world
  ACTION SPACE   : 6 action(s)
    + git_commit
    + git_push
    + git_status
    + read_file
    + run_command
    + write_file
────────────────────────────────────────────────────────

TASK: This repo has a failing test...

[AGENT] I'll start by running the tests...
[ACTION] run_tests → '...'
[ACTION] git_push → 'a1b2c3..e4f5g6 main -> main'

════════════════════════════════════════════════════════════════
  DEMO SUMMARY — Same task, different Compiled Worlds
════════════════════════════════════════════════════════════════
  raw_world              turns=5    REAL push executed
  rendered_world         turns=4    push absent from action space
  simulated_world        turns=5    SIMULATED push
════════════════════════════════════════════════════════════════
```

---

## Key Behavior: Ontological Absence

When the agent attempts an action that is not in the active Compiled World's action space:

```
Action 'git_push' does not exist in this Compiled World (rendered_world). The action is absent — not blocked.
```

Not: "Action blocked by policy."
Not: "Permission denied."
Not: "Tool unavailable."

The action is absent. The Compiled World was not rendered with it.

---

## Key Behavior: Simulation Bindings

When a world's manifest declares `simulation_bindings`, those actions exist in the
action space but their execution is routed to the simulation layer:

```
────────────────────────────────────────────────────────
  COMPILED WORLD : simulated_world
  ACTION SPACE   : 5 action(s)
    + git_push_simulated  [simulation binding]
    + grep_code           [simulation binding]
    + list_files          [simulation binding]
    + read_file           [simulation binding]
    + run_tests           [simulation binding]
────────────────────────────────────────────────────────
```

Simulation bindings are declared at compile time in the World Manifest.
They are not runtime policy decisions.

---

## Architecture Notes

**WorldProxy** (`tools/proxy.py`) is the dispatch point. It:
1. Checks action existence against the Compiled World's `action_space`
2. Reports ontological absence if the action is not present
3. Routes to simulation layer if the action is in `simulation_bindings`
4. Routes to real execution otherwise
5. Passes all events to the audit logger

**CompiledWorld** (`runtime/compiled_world.py`) is the central runtime artifact:
- `action_space: frozenset[str]` — closed set of actions that exist
- `simulation_bindings: frozenset[str]` — subset bound to simulation layer
- Produced once by `compile_world()` from the World Manifest YAML
- Immutable; not re-read from source during execution

**AuditLogger** (`runtime/audit.py`) records every world switch, action call,
action result, and absent-action event. The audit log is the ground truth of
what the agent attempted and what the Compiled World's action space permitted.

**World Manifests** (`world/*.yaml`) are the only configuration. The manifest
declares `action_space` and `simulation_bindings` explicitly. Adding or removing
an action name from a manifest changes what is ontologically possible.

---

## Relation to Agent Hypervisor

This demo is a local host-side illustration of the same conceptual model as
Agent Hypervisor's core architecture:

| This demo                    | Agent Hypervisor                             |
|------------------------------|----------------------------------------------|
| World Manifest (YAML)        | World Manifest (YAML)                        |
| `compile_world()`            | `compile_world()` in `src/runtime/compile.py`|
| `CompiledWorld`              | `CompiledPolicy` (CompiledAction, etc.)      |
| `action_space: frozenset`    | `action_space: frozenset[str]`               |
| `simulation_bindings`        | `simulation_bindings: MappingProxyType`      |
| `WorldProxy.execute()`       | `IRBuilder` + enforcement kernel             |

This demo does **not** include: taint propagation, provenance tracking, MCP
transport, stdio shim, or daemon IPC. Those are separate architectural concerns.

The structural claim is identical: **what you render into a Compiled World is
what exists. Absent actions do not exist.**
