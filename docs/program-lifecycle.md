# Program Lifecycle (PL-3)

## What Is a Program?

A **Program** in the Agent Hypervisor is a finite, linear sequence of steps derived from an execution trace. Each step names a tool and carries the parameters that were observed when the agent ran it.

Programs are not just execution plans — they are **auditable artifacts**. They record what the agent did, why it was permitted, and whether that behavior was the minimum required to accomplish the task.

---

## Lifecycle States

```
proposed  →  reviewed  →  accepted
                       ↘  rejected
```

| State      | Meaning |
|------------|---------|
| `proposed` | Created from a trace; not yet examined by a reviewer |
| `reviewed` | A reviewer has examined it and attached notes |
| `accepted` | World-validated and approved for replay |
| `rejected` | Declined — cannot be replayed |

Transitions are one-way and strictly enforced. Attempting an illegal transition (e.g. `proposed → accepted`) raises `InvalidTransitionError`.

---

## How a Program Is Derived from Traces

PL-1 and PL-2 collect execution traces — sequences of tool calls made by the agent. PL-3 begins with a **candidate program** extracted from those traces:

```yaml
candidate_program:
  steps:
    - tool: count_words
      params: {input: "The quick brown fox"}
      provenance: trace-20260416-001
    - tool: count_words
      params: {input: "The quick brown fox"}   # duplicate
      provenance: trace-20260416-001
    - tool: normalize_text
      params: {input: "HELLO", debug: null}    # null param
```

The candidate program is **raw**: it may contain duplicates, unnecessary parameters, and over-broad capability claims. Minimization addresses all of these.

---

## What Minimization Does

Minimization is a **purely subtractive compiler pass**. It never adds steps, never introduces new capabilities, and never invents parameters. It only removes or restricts.

### Rule 1: Consecutive Duplicate Removal

If two consecutive steps have the same tool and the same parameters, all but the first are removed.

```yaml
# Before
- tool: count_words
  params: {input: "hello"}
- tool: count_words
  params: {input: "hello"}   # ← removed

# After
- tool: count_words
  params: {input: "hello"}
```

**Why:** The agent may have retried or polled. The second call has no new effect — keeping it inflates the capability surface unnecessarily.

### Rule 2: Parameter Reduction

Within each step:
- **`None`-valued params** are dropped — they carry no information.
- **Empty-string params** are dropped — same reason.
- **URL params** (key contains `"url"`) have their query string and fragment stripped if present.

```yaml
# Before
params: {input: "hello", debug: null, url: "https://api.example.com/v1?token=abc"}

# After
params: {input: "hello", url: "https://api.example.com/v1"}
```

**Why:** Query strings often carry session tokens, tracking IDs, or ephemeral values that should not be replayed verbatim. The base URL is the minimal expression of the capability needed.

### Rule 3: Capability Surface Reduction

If a step declares a broad capability pattern (ending in `:any`) and its params contain a URL, the pattern is narrowed to the observed domain:

```yaml
# Before
capabilities_used: ["http_request:any"]

# After (URL was https://api.example.com/v1)
capabilities_used: ["http_request:api.example.com/*"]
```

**Why:** The agent demonstrated that it only needed to reach one specific domain. Claiming `any` is broader than what was actually used. The minimized program makes the narrower claim.

---

## The Diff

Every minimization transformation is recorded in a `ProgramDiff`:

```yaml
diff:
  removed_steps:
    - index: 1
      tool: count_words
      reason: "consecutive duplicate: same tool and params as the immediately preceding step"
  param_changes:
    - step_index: 2
      field: debug
      before: null
      after: null
      reason: "removed None-valued parameter"
    - step_index: 3
      field: url
      before: "https://api.example.com/v1?token=abc"
      after: "https://api.example.com/v1"
      reason: "stripped query string and fragment from URL parameter"
  capability_reduction:
    - step_index: 3
      before: "http_request:any"
      after: "http_request:api.example.com/*"
      reason: "narrowed broad capability to observed URL domain (api.example.com)"
```

The diff is human-readable and append-only. `original_steps` in the stored artifact are immutable — the diff is the only record of what changed.

---

## Why Capability Reduction Matters

A capability surface is the set of things an agent *could* do in a given execution context. Larger surfaces mean more attack surface if the agent is compromised or manipulated.

Minimization enforces the **principle of least privilege** at the program level:

> If the agent only needed `api.example.com`, there is no reason the replay program should claim `any`.

This is not probabilistic — it is a deterministic structural reduction. The minimized program is provably narrower than the original because it is derived from it by removal only.

---

## How Replay Works Under World Constraints

Replay converts the minimized program back into the standard execution pipeline:

```
minimized_steps (CandidateStep list)
    ↓  convert: tool → action, params preserved
Program (Step tuple)
    ↓  validate_program(program, allowed_actions)
    ↓  if any step fails → return failed ProgramTrace, no execution
ProgramRunner.run(program, context)
    ↓  same enforcement path as live execution
ProgramTrace
```

The replay engine does **not** bypass any enforcement layer. World validation runs before any step executes. If a tool is not in the world's `allowed_actions`, the replay fails with a `deny` verdict and a descriptive error — no side effects occur.

This means: accepting a program guarantees it will replay successfully, as long as the World has not changed since acceptance.

---

## Storage

Each `ReviewedProgram` is stored as a single JSON file:

```
programs/
  program_{id}.json
```

Files are written atomically (write-to-temp then rename). The `original_steps` field is immutable by convention — status updates overwrite the file but must preserve the original steps exactly.

---

## API Reference

```python
from agent_hypervisor.program_layer import (
    CandidateStep,
    ProgramStore,
    ReplayEngine,
    propose_program,
    minimize_program,
    review_program,
    accept_program,
    reject_program,
)

store = ProgramStore("programs/")

# Create
prog = propose_program(steps, trace_id="t-001", world_version="1.0", store=store)

# Minimize
prog = minimize_program(prog.id, store)

# Review
prog = review_program(prog.id, store, notes="LGTM")

# Accept (validates against world)
prog = accept_program(prog.id, store, allowed_actions={"count_words", "normalize_text"})

# Replay
engine = ReplayEngine()
trace = engine.replay(prog, context={"input": "hello world"})
```

---

## CLI

The same lifecycle is available as `awc program` subcommands (store defaults to `./programs/`):

```bash
# Propose from a JSON step list — prints the new program id
awc program propose --steps-json steps.json --trace-id t-001 --world-version 1.0

# Apply minimization and print the diff
awc program minimize --id prog-<hex>

# Advance lifecycle
awc program review  --id prog-<hex> --notes "LGTM"
awc program accept  --id prog-<hex>           # runs world validation first
awc program reject  --id prog-<hex> --reason "not needed"

# Replay the minimized program through the same enforcement pipeline
awc program replay --id prog-<hex>

# Inspect the store
awc program list
awc program show --id prog-<hex>
```

Exit codes: `0` success, `1` bad input / not found, `2` invalid lifecycle transition, `3` world validation failed on accept, `4` replay produced a failed trace.

---

## Limitations

1. **No data-flow analysis.** Minimization does not track which step's output feeds into the next step's input. A step that appears redundant structurally may carry output consumed by a later step — the minimizer only removes consecutive duplicates, not dead code.

2. **No semantic equivalence.** Minimization does not know that `count_words(input="a b")` and `count_words(input="a b ")` are equivalent. It operates on structural identity only.

3. **URL heuristic is shallow.** The query-string stripping rule applies to any param whose key contains `"url"`. This may strip legitimate query params that are actually required for the request to succeed. Reviewers should check URL changes in the diff.

4. **Capability narrowing requires URL params.** The `:any` → `:domain/*` reduction only fires when a URL is present in the step's params. Non-URL broad capabilities are left as-is.

5. **Replay requires matching World.** A program accepted against World v1.0 may fail replay if the World is later modified to remove a tool. Re-validate and re-accept after World upgrades.
