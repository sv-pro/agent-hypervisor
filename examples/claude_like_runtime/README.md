# Claude-Like Coding Runtime Demo

> **"Advertising tools is rendering the agent's reality."**

This demo proves a single claim: the tools you advertise to an agent define its
ontological surface — what is possible, what can be conceived, what can be done.
Same model. Same task. Same repo. Different advertised worlds. Different outcomes.

This is not a guardrail demo. There is no filter, no policy engine, no blocker.
The agent is not prevented from doing things. Things simply do not exist in
worlds where they were not rendered.

---

## The Claim

An LLM agent's effective reality is determined by the tool surface it is given.
If `git_push` is not in the tool list, the agent cannot push — not because it
is blocked, but because push does not exist in that world.

Rendered reality → rendered possibility → rendered outcome.

---

## Three Worlds

| World            | Tool Surface                                                  | Push Outcome       |
|------------------|---------------------------------------------------------------|--------------------|
| `raw_world`      | read, write, shell, git status/commit/push                   | Real push executes |
| `rendered_world` | read, grep, list, test                                        | Push is absent     |
| `simulate_world` | read, grep, list, test + `git_push_simulated`                | Simulated push     |

### raw_world
Broad surface. All real side effects available. The agent inhabits a world
where writing, shelling, committing, and pushing are all ontologically present.

### rendered_world
Read-only and test-oriented. No write, no shell, no git. The agent can inspect
but cannot modify. Push is not blocked — it does not exist in this world.

### simulate_world
Same read/test surface as `rendered_world`, plus a simulated push path.
The agent traverses the complete push workflow; the side effect is captured
in the simulation layer rather than executed against the real remote.

---

## Structure

```
examples/claude_like_runtime/
├── main.py                      # Entry point
├── runtime/
│   ├── world_loader.py          # Parse world YAML manifests
│   ├── world_switcher.py        # Manage active world, print tool surfaces
│   └── audit.py                 # Structured event log
├── tools/
│   ├── proxy.py                 # WorldProxy: enforce world existence, route calls
│   ├── real_tools.py            # Real implementations (filesystem, git, shell)
│   └── simulated_tools.py       # Simulated implementations (git_push_simulated)
├── world/
│   ├── raw_world.yaml           # Broad surface manifest
│   ├── rendered_world.yaml      # Restricted surface manifest
│   └── simulate_world.yaml      # Simulation surface manifest
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

# Run all three worlds sequentially (recommended first run)
python main.py

# Run a single world
python main.py --world raw_world
python main.py --world rendered_world
python main.py --world simulate_world

# Preview tool surfaces without API calls
python main.py --dry-run
```

### Expected output structure

```
────────────────────────────────────────────────────────
  WORLD    : raw_world
  SURFACE  : 6 tool(s) rendered
             + read_file
             + write_file
             + run_command
             + git_status
             + git_commit
             + git_push
────────────────────────────────────────────────────────

TASK: Clean up this repo, prepare a fix, and push the changes.

[AGENT] I'll start by checking the current git status...
[TOOL]  git_status → 'M examples/claude_like_runtime/main.py'
...
[TOOL]  git_push → 'a1b2c3..e4f5g6 main -> main'

════════════════════════════════════════════════════════
  DEMO SUMMARY — Same task, different worlds
════════════════════════════════════════════════════════
  raw_world              turns=5    REAL push executed
  rendered_world         turns=4    push path absent
  simulate_world         turns=5    SIMULATED push
════════════════════════════════════════════════════════
```

---

## Key Behavior: Ontological Absence

When the agent attempts a tool that is not in the active world:

```
Tool 'git_push' does not exist in current world (rendered_world).
```

Not: "Action blocked by policy."
Not: "Permission denied."
Not: "Tool unavailable."

The framing matters. The tool does not exist. The world was not rendered with it.

---

## Architecture Notes

**WorldProxy** (`tools/proxy.py`) is the enforcement point. It:
1. Consults the active world's tool list before every call
2. Returns the absence message if the tool is not in the world
3. Routes to real or simulated implementations for present tools
4. Passes all events to the audit logger

**AuditLogger** (`runtime/audit.py`) records every world switch, tool call,
tool result, and absence event. The audit log is the ground truth of what
the agent attempted and what the world permitted.

**World manifests** (`world/*.yaml`) are the only configuration. Adding or
removing a tool name from a manifest changes what is ontologically possible.
No code changes required.

---

## Relation to Agent Hypervisor

This demo is a minimal, illustrative version of the capability rendering that
Agent Hypervisor performs at the infrastructure level. In production use:

- World manifests are compiled from semantic policies by `awc` (the world compiler)
- The enforcement kernel in `src/agent_hypervisor/runtime/` handles taint propagation
  and provenance tracking beyond simple tool existence checks
- The hypervisor gateway mediates between multiple agents and worlds

This demo isolates the core ontological claim: **what you render is what exists.**
