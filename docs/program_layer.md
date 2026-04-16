# Program Layer — Phase 1

The Program Layer is an optional, pluggable execution abstraction that sits above the World Kernel. It allows execution to be driven by a **structured, linear program** rather than a single direct tool call.

All policy enforcement happens in the World Kernel before the program layer is ever reached. The program layer defines *how* a task executes within the boundaries already established by the world manifest; it never re-evaluates or overrides policy.

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

```python
from agent_hypervisor.program_layer import Program, Step

program = Program(
    program_id="analysis-v1",
    steps=(
        Step(action="count_words", params={"input": "hello world foo"}),
        Step(action="normalize_text", params={"input": "HELLO WORLD"}),
    ),
)
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

The runner never re-evaluates policy. The `allowed_actions` set passed to the runner represents post-enforcement knowledge from the world.

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

---

## Supported Actions (Phase 1)

Phase 1 supports four **named workflows** compiled deterministically — no LLM, no synthesis:

| Action | Input | Output |
|--------|-------|--------|
| `count_lines` | `input: str` | `{line_count, non_empty_line_count, char_count}` |
| `count_words` | `input: str` | `{word_count, line_count, char_count}` |
| `normalize_text` | `input: str` | `{normalized, line_count, char_count}` |
| `word_frequency` | `input: str`, `top_n: int` (opt, 1–100, default 10) | `{top_words, unique_word_count, total_word_count}` |

All workflows execute inside the `SandboxRuntime` — a restricted Python environment with AST-level security validation and a hard wall-clock timeout.

---

## Sandbox Constraints

The `SandboxRuntime` enforces:

- **No imports** — `import` and `from...import` are blocked at the AST level
- **No dangerous builtins** — `eval`, `exec`, `open`, `getattr`, `globals`, `locals`, and others are not available
- **No dunder attribute access** — `__builtins__`, `__class__`, `__dict__`, etc. are blocked
- **Hard timeout** — programs exceeding `timeout_seconds` (default 5.0) are killed; verdict → `deny`
- **Explicit bindings only** — programs can only call functions explicitly injected (`read_input`, `emit_result`, `json_dumps`, `json_loads`)

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

Check the flag before using the layer:

```python
from agent_hypervisor.program_layer import ENABLE_PROGRAM_LAYER, ProgramRunner

if ENABLE_PROGRAM_LAYER:
    runner = ProgramRunner(allowed_actions={"count_words"})
    trace = runner.run(program)
```

---

## Execution Flow

```
Program (frozen dataclass)
    ↓
ProgramRunner.run()
    │
    ├── for each Step:
    │     ├── 1. Validate action ∈ allowed_actions    → deny + abort if not found
    │     ├── 2. DeterministicTaskCompiler.compile()  → ProgramExecutionPlan
    │     ├── 3. ProgramExecutor.execute()             → sandbox execution
    │     │       └── SandboxRuntime.run()
    │     │             ├── AST security validation
    │     │             ├── Compile to code object
    │     │             ├── Build restricted globals + filtered bindings
    │     │             └── exec() in daemon thread (timeout enforced)
    │     └── StepTrace (allow | deny | skip)
    │
    └── ProgramTrace (ok, step_traces, aborted_at_step, total_duration_seconds)
```

---

## What Is Intentionally Not In Phase 1

| Not implemented | Reason |
|----------------|---------|
| Branching / loops in programs | Determinism and auditability require linear structure |
| LLM-generated program steps | No LLM on the enforcement path |
| Data flow between steps | Steps are independent; output-to-input wiring is planned for Phase 2 |
| ProgramRegistry (store/load) | Stub only; reviewed program attestation is future work |
| Arbitrary Python actions | Only the 4 pre-written workflows are supported in Phase 1 |
| World-aware action validation | `allowed_actions` is caller-supplied; deeper world integration is Phase 2 |

---

## API Reference

### `Step(action: str, params: dict = {})`

Frozen dataclass. Raises `ValueError` if `action` is empty.

### `Program(program_id: str, steps: tuple[Step, ...])`

Frozen dataclass. Raises:
- `ValueError` if `program_id` is empty, steps is empty, or `len(steps) > MAX_STEPS (10)`
- `TypeError` if steps is not a tuple or contains non-Step elements

### `ProgramRunner(allowed_actions=None, default_timeout=5.0, compiler=None, executor=None)`

- `allowed_actions`: set of permitted action names (default: `DeterministicTaskCompiler.SUPPORTED_WORKFLOWS`)
- `default_timeout`: per-step wall-clock limit in seconds (must be positive)
- `compiler` / `executor`: injectable dependencies for testing

### `ProgramRunner.run(program: Program, context: dict = None) → ProgramTrace`

Executes the program and returns the trace. Never raises (errors are captured in `StepTrace.error`), except:
- `TypeError` if `program` is not a `Program` instance

### `ENABLE_PROGRAM_LAYER: bool`

Feature flag. Default `True`. Set `AGENT_HYPERVISOR_ENABLE_PROGRAM_LAYER=0` to disable.

### `MAX_STEPS: int`

Maximum steps allowed per program. Currently `10`.
