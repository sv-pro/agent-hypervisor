# Program Layer — Phase 1: Executable Programs

The Program Layer is an optional, pluggable execution abstraction that sits above the World Kernel. It allows execution to be driven by a **structured, linear program** rather than a single direct tool call.

All policy enforcement happens in the World Kernel before the program layer is ever reached. The program layer defines *how* a task executes within the boundaries already established by the world manifest; it never re-evaluates or overrides policy.

**Core principle:** Programs orchestrate. The World Kernel decides what is possible.

---

## Execution Flow

```
intent
    ↓
SimpleTaskCompiler.compile(intent, world)   ← keyword matching / dict dispatch
    ↓
ProgramExecutionPlan (or DirectExecutionPlan fallback)
    ↓
validate_program(program, allowed_actions)  ← static pre-execution check
    ↓  (if ok)
ProgramRunner.run(program, context)
    │
    ├── for each Step:
    │     ├── 1. Check action ∈ allowed_actions          → deny + abort if not
    │     ├── 2. DeterministicTaskCompiler.compile()     → ProgramExecutionPlan
    │     ├── 3. ProgramExecutor.execute()               → sandbox execution
    │     │       └── SandboxRuntime.run()
    │     │             ├── AST security validation
    │     │             ├── Compile to code object
    │     │             ├── Restricted globals + filtered bindings
    │     │             └── exec() in daemon thread (timeout enforced)
    │     └── StepTrace (allow | deny | skip)
    │
    └── ProgramTrace (ok, step_traces, aborted_at_step, total_duration_seconds)
    ↓
ProgramTraceStore.append(trace)             ← JSONL persistence
```

If `ENABLE_PROGRAM_LAYER = False`, the system falls back to `DirectExecutionPlan` (existing behavior, unchanged).

---

## Core Concepts

### Program and Step

A **Program** is a finite, ordered sequence of **Steps**. There are no branches, loops, or dynamic control flow. Every program is:

- **Linear** — steps run in strict order (index 0 first)
- **Bounded** — at most `MAX_STEPS` (10) steps per program
- **Frozen** — immutable after construction; cannot be modified at runtime

A **Step** specifies:
- `action` — the action name to invoke (matched against the world's allowed set)
- `params` — key-value parameters forwarded to the executor (e.g. `{"input": "text..."}`)
- `description` — optional human-readable note (no effect on execution; excluded from equality/hash)

```python
from agent_hypervisor.program_layer import Program, Step

program = Program(
    program_id="analysis-v1",
    steps=(
        Step(
            action="count_words",
            params={"input": "hello world foo"},
            description="Count words in the input text",
        ),
        Step(
            action="normalize_text",
            params={"input": "HELLO WORLD"},
            description="Lowercase and strip whitespace",
        ),
    ),
)
```

### SimpleTaskCompiler

**SimpleTaskCompiler** translates a loosely-structured intent (string or dict) into an `ExecutionPlan` using deterministic keyword matching. No LLM, no probabilistic scoring.

```python
from agent_hypervisor.program_layer import SimpleTaskCompiler

compiler = SimpleTaskCompiler()

# String intent → keyword matching
plan = compiler.compile("count the words in this document")
# → ProgramExecutionPlan(workflow="count_words", ...)

# Dict intent → delegated to DeterministicTaskCompiler
plan = compiler.compile({"workflow": "count_lines"})
# → ProgramExecutionPlan(workflow="count_lines", ...)

# Unknown intent → safe fallback
plan = compiler.compile("send email to alice@example.com")
# → DirectExecutionPlan(...)   (no capability granted, no error)

# World-filtered: only emit plans for workflows the world allows
plan = compiler.compile("count words", world=frozenset({"count_lines"}))
# → DirectExecutionPlan(...)   (count_words not in world)
```

Supported `world` argument shapes:
- `None` — no constraint
- `frozenset[str]` or `set[str]` — used directly as allowed workflow set
- Object with `allowed_workflows` attribute
- Object with `action_space` attribute (e.g. `CompiledPolicy`) — intersected with `SUPPORTED_WORKFLOWS`

### World Validation

**`validate_program()`** performs a static pre-execution check of every step before any step runs. This is stricter than the step-by-step abort in `ProgramRunner` — it catches all violations upfront before any side effects occur.

```python
from agent_hypervisor.program_layer import validate_program
from agent_hypervisor.program_layer import DeterministicTaskCompiler

result = validate_program(program, DeterministicTaskCompiler.SUPPORTED_WORKFLOWS)
if not result.ok:
    for v in result.violations:
        print(f"DENY: {v}")   # "step[1] action='send_email': action not in allowed set; allowed: [...]"
else:
    trace = runner.run(program)
```

`ValidationResult` fields:
- `ok: bool` — True only if all steps pass
- `violations: tuple[StepViolation, ...]` — one entry per failing step

`StepViolation` fields:
- `step_index: int` — 0-based position
- `action: str` — the rejected action name
- `reason: str` — human-readable explanation

For single-step validation:

```python
from agent_hypervisor.program_layer import validate_step
violation = validate_step(step, allowed_actions=frozenset({"count_words"}), step_index=0)
# None if valid, StepViolation if rejected
```

### ProgramRunner

**ProgramRunner** executes a Program step by step and returns a **ProgramTrace**.

```python
from agent_hypervisor.program_layer import ProgramRunner

runner = ProgramRunner(allowed_actions={"count_words", "normalize_text"})
trace = runner.run(program)
```

Execution contract:

1. **Validate action** — step.action must be in `allowed_actions`. Unknown actions → `deny` verdict; runner aborts.
2. **Compile** — action is compiled to a `ProgramExecutionPlan` via `DeterministicTaskCompiler`.
3. **Execute** — plan runs inside the AST-validated sandbox (`SandboxRuntime`).
4. **Abort on deny** — any denied step causes all remaining steps to get verdict `skip`.

The runner never re-evaluates policy. The `allowed_actions` set represents post-enforcement knowledge from the world.

### ProgramTrace and StepTrace

**ProgramTrace** records the full execution outcome:

| Field | Type | Meaning |
|-------|------|---------|
| `program_id` | `str` | Matches `Program.program_id` |
| `step_traces` | `list[StepTrace]` | One per step in the program |
| `ok` | `bool` | `True` only if all steps are `allow` |
| `total_duration_seconds` | `float` | Wall-clock time for the full run |
| `aborted_at_step` | `int \| None` | Index of the first denied step |

**StepTrace** records each step:

| Field | Type | Meaning |
|-------|------|---------|
| `step_index` | `int` | 0-based position in the program |
| `action` | `str` | The step's action name |
| `verdict` | `"allow" \| "deny" \| "skip"` | Outcome |
| `result` | `Any` | Step output (None if denied/skipped) |
| `error` | `str \| None` | Error/denial message |
| `duration_seconds` | `float` | Wall-clock time for this step |

```python
if trace.ok:
    for st in trace.step_traces:
        print(f"{st.action}: {st.result}")
else:
    failed = next(st for st in trace.step_traces if st.denied)
    print(f"Step {failed.step_index} ({failed.action}) denied: {failed.error}")
```

### JSONL Trace Storage

**ProgramTraceStore** persists execution traces to a JSONL file (one JSON object per line, append-only).

```python
from agent_hypervisor.program_layer import ProgramTraceStore

store = ProgramTraceStore("traces/program_traces.jsonl")

# Persist a trace
trace = runner.run(program)
store.append(trace)

# Read recent traces (newest first)
recent = store.list_recent(limit=10)
for entry in recent:
    print(entry["program_id"], entry["ok"])

# Filter by outcome
failures = store.list_recent(ok=False)
for program_traces in store.list_recent(program_id="analysis-v1"):
    print(program_traces)
```

Each stored entry is `ProgramTrace.to_dict()` plus a `_stored_at` ISO-8601 timestamp.

---

## Example: ProgramExecutionPlan

```python
ProgramExecutionPlan(
    plan_id="prog-count_words-a1b2c3d4",
    language="python",
    program_source="""
text = read_input()
words = text.split()
lines = text.splitlines()
emit_result({
    "word_count": len(words),
    "line_count": len(lines),
    "char_count": len(text),
})
""",
    allowed_bindings=("read_input", "emit_result", "json_dumps", "json_loads"),
    timeout_seconds=5.0,
    metadata={"workflow": "count_words", "compiled_by": "DeterministicTaskCompiler"},
)
```

---

## Example: Execution Trace (JSONL line)

```json
{
  "program_id": "analysis-v1",
  "ok": true,
  "total_duration_seconds": 0.012,
  "aborted_at_step": null,
  "step_traces": [
    {
      "step_index": 0,
      "action": "count_words",
      "verdict": "allow",
      "result": {"word_count": 3, "line_count": 1, "char_count": 15},
      "error": null,
      "duration_seconds": 0.006
    },
    {
      "step_index": 1,
      "action": "normalize_text",
      "verdict": "allow",
      "result": {"normalized": "hello world", "line_count": 1, "char_count": 11},
      "error": null,
      "duration_seconds": 0.004
    }
  ],
  "_stored_at": "2024-01-01T00:00:00.000000+00:00"
}
```

Denied trace example:

```json
{
  "program_id": "unsafe-prog",
  "ok": false,
  "total_duration_seconds": 0.001,
  "aborted_at_step": 0,
  "step_traces": [
    {
      "step_index": 0,
      "action": "send_email",
      "verdict": "deny",
      "result": null,
      "error": "action 'send_email' is not in the allowed action set; allowed: ['count_lines', 'count_words', 'normalize_text', 'word_frequency']",
      "duration_seconds": 0.0
    },
    {
      "step_index": 1,
      "action": "count_words",
      "verdict": "skip",
      "result": null,
      "error": "execution aborted by a prior denied step",
      "duration_seconds": 0.0
    }
  ],
  "_stored_at": "2024-01-01T00:00:01.000000+00:00"
}
```

---

## Supported Actions (Phase 1)

Phase 1 supports four **named workflows** compiled deterministically — no LLM, no synthesis:

| Action | Input | Output |
|--------|-------|--------|
| `count_lines` | `input: str` | `{line_count, non_empty_line_count, char_count}` |
| `count_words` | `input: str` | `{word_count, line_count, char_count}` |
| `normalize_text` | `input: str` | `{normalized, line_count, char_count}` |
| `word_frequency` | `input: str`, `top_n: int` (opt, 1–100, default 10) | `{top_words, unique_word_count, total_word_count}` |

All workflows execute inside the `SandboxRuntime`.

---

## How Validation Works

There are two independent validation layers:

### 1. Static pre-validation (`validate_program`)

Before execution starts, `validate_program(program, allowed_actions)` checks every step's `action` against the allowed set. This is a pure, deterministic check:

- Iterates all steps; collects ALL violations before returning
- Returns `ValidationResult(ok=False, violations=[...])` if any step fails
- Caller can gate execution: do not call `runner.run()` if `result.ok is False`
- Completely independent of the sandbox; runs in microseconds

### 2. Runtime per-step validation (`ProgramRunner`)

During execution, `ProgramRunner._execute_step()` re-validates each step immediately before compiling it:

- If action not in `allowed_actions` → `StepTrace(verdict="deny")`, runner aborts
- If compiler cannot produce a `ProgramExecutionPlan` → `StepTrace(verdict="deny")`, runner aborts
- If sandbox raises any error → `StepTrace(verdict="deny")`, runner aborts
- Runner is fail-closed: errors become `deny` verdicts, never propagate as exceptions

The two layers are complementary: static pre-validation gives the caller an upfront picture; runtime validation is the hard gate.

---

## How the Sandbox Is Enforced

The `SandboxRuntime` enforces four independent constraints:

| Constraint | Mechanism | Failure mode |
|-----------|-----------|-------------|
| No imports | AST visitor: `visit_Import`, `visit_ImportFrom` | `SandboxSecurityError` at parse time |
| No dangerous builtins | `_FORBIDDEN_CALL_NAMES` checked in AST visitor | `SandboxSecurityError` at parse time |
| No dunder attribute access | `_FORBIDDEN_ATTRS` checked in AST visitor | `SandboxSecurityError` at parse time |
| Hard timeout | Daemon thread + `thread.join(timeout)` | `SandboxTimeoutError` after `timeout_seconds` |

AST validation runs before `exec()` — no code is ever executed if the AST check fails. The safe builtins whitelist (66 names) is explicit: programs only see what is listed in `_SAFE_BUILTINS_NAMES`. Everything else is absent from the program's namespace; access produces `NameError`.

---

## Feature Flag

The program layer is enabled by default. Disable it with:

```bash
AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER=0 python my_script.py
```

Or at runtime:

```python
import agent_hypervisor.program_layer.config as program_config
program_config.ENABLE_PROGRAM_LAYER = False
```

When disabled, callers should bypass the program layer entirely:

```python
from agent_hypervisor.program_layer import ENABLE_PROGRAM_LAYER, ProgramRunner

if ENABLE_PROGRAM_LAYER:
    runner = ProgramRunner(allowed_actions={"count_words"})
    trace = runner.run(program)
else:
    # fall back to direct execution (existing behavior)
    ...
```

---

## Phase 1 Limitations

| Limitation | Reason |
|-----------|--------|
| No branching or loops in programs | Determinism and auditability require linear structure |
| No LLM-generated program steps | No LLM on the enforcement path |
| No data flow between steps | Steps are independent; output-to-input wiring is planned for Phase 2 |
| `SimpleTaskCompiler` uses keyword matching, not NLP | Deterministic; no probabilistic scoring |
| `ProgramRegistry.store()` / `.load()` not implemented | Stub only; reviewed program attestation is future work |
| Only 4 pre-written workflows | Arbitrary Python programs are not accepted; custom workflows require Phase 2 |
| World validation checks action name only | Deep capability matrix validation (trust level × action type) is Phase 2 |
| `SandboxRuntime` timeout uses daemon thread | Timed-out thread continues running until process exit (CPython limitation) |
| No cross-step context sharing | Each step receives independent input; no shared state between steps |
| JSONL store is not thread-safe | Single-process use only; shared storage requires external locking |

---

## API Reference

### `Step(action: str, params: dict = {}, description: Optional[str] = None)`

Frozen dataclass. `description` is for display only; excluded from equality and hash.
Raises `ValueError` if `action` is empty.

### `Program(program_id: str, steps: tuple[Step, ...])`

Frozen dataclass. Raises:
- `ValueError` if `program_id` is empty, steps is empty, or `len(steps) > MAX_STEPS (10)`
- `TypeError` if steps is not a tuple or contains non-Step elements

### `SimpleTaskCompiler(extra_patterns=())`

- `compile(intent, world=None)` → `ExecutionPlan`
- String intents: keyword-matched to a workflow; first match wins
- Dict intents: delegated to `DeterministicTaskCompiler`
- Unknown/unmatched intents: `DirectExecutionPlan` fallback
- `world` filters which workflows may be emitted

### `validate_program(program: Program, allowed_actions: Collection[str]) → ValidationResult`

Static pre-execution check. Returns `ValidationResult(ok=True)` if every step's action is in `allowed_actions`, `ValidationResult(ok=False, violations=(...))` otherwise. Collects all violations before returning. Raises `TypeError` if `program` is not a `Program`.

### `validate_step(step: Step, allowed_actions, step_index: int = 0) → Optional[StepViolation]`

Single-step variant. Returns `None` if valid, `StepViolation` if rejected.

### `ProgramRunner(allowed_actions=None, default_timeout=5.0, compiler=None, executor=None)`

- `allowed_actions`: set of permitted action names (default: `DeterministicTaskCompiler.SUPPORTED_WORKFLOWS`)
- `default_timeout`: per-step wall-clock limit in seconds (must be positive)
- `compiler` / `executor`: injectable dependencies for testing
- `run(program, context=None)` → `ProgramTrace` — never raises (errors are captured in `StepTrace.error`), except `TypeError` if `program` is not a `Program`

### `ProgramTraceStore(path: str | Path)`

- `append(trace: ProgramTrace)` — persist to JSONL, creates file and parent dirs
- `list_recent(limit=50, ok=None, program_id=None)` → `list[dict]` — newest first
- `count()` → `int` — total stored traces
- Raises `TypeError` for non-`ProgramTrace` arguments to `append()`

### `ENABLE_PROGRAM_LAYER: bool`

Feature flag. Default `True`. Set `AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER=0` to disable.

### `MAX_STEPS: int`

Maximum steps allowed per program. Currently `10`.
