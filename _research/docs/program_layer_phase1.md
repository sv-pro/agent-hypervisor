# Program Layer — Phase 1 Implementation

*What was built, what works, what was deliberately left out.*

---

## What Phase 1 Adds

Phase 1 turns the program layer scaffolding (introduced as stubs) into a real,
working execution path. Three components are now functional:

| Component | File | Status |
|-----------|------|--------|
| `SandboxRuntime` | `program_layer/sandbox_runtime.py` | **New** |
| `DeterministicTaskCompiler` | `program_layer/task_compiler.py` | **New** |
| `ProgramExecutor` | `program_layer/program_executor.py` | **Replaced stub** |
| `ProgramExecutionPlan` | `program_layer/execution_plan.py` | **Extended** |
| Gateway integration | `hypervisor/gateway/execution_router.py` | **Updated** |

---

## What Remains Unchanged

Everything in the World Kernel is untouched:

- `runtime/` — IRBuilder, taint, channel, executor, worker
- `hypervisor/firewall.py` — ProvenanceFirewall (RULE-01–05)
- `hypervisor/policy_engine.py` — declarative YAML rules
- `hypervisor/provenance.py` — provenance resolution utilities
- All existing demos, examples, and tests continue to pass

The direct execution path (`plan_type="direct"`, the default) produces
byte-for-byte identical results to the pre-Phase-1 state.

---

## Two Execution Paths

```
Intent / tool request
    │
    ▼  World Kernel (unchanged)
    │  • IRBuilder constraint checks
    │  • PolicyEngine (YAML rules)
    │  • ProvenanceFirewall (RULE-01–05)
    │  • Taint propagation
    │
    ▼  verdict == "allow"
    │
    ├── plan_type == "direct"  (default)
    │       → tool_def.adapter(raw_args)
    │         existing behaviour, no new code
    │
    └── plan_type == "program"
            → DeterministicTaskCompiler.compile(intent)
              OR use supplied program_source directly
            → ProgramExecutor.execute(plan, context)
            → SandboxRuntime.run(program_source, input_value)
            → structured result dict
```

The new path is **opt-in only**. Callers that do not set `plan_type="program"`
are completely unaffected.

---

## Sandbox Runtime

`SandboxRuntime` provides a minimal restricted execution environment using
Python's `exec()` with a heavily constrained namespace.

### What it allows

- Safe built-in functions: arithmetic, string ops, list/dict/set, iteration,
  type checking — see `_SAFE_BUILTINS_NAMES` in `sandbox_runtime.py`
- Exception handling (`try/except`) with safe exception types
- Injected bindings: `read_input()`, `emit_result()`, `json_dumps()`, `json_loads()`

### What it blocks (hard, at AST validation before any exec())

| Forbidden | How it's blocked |
|-----------|-----------------|
| `import` / `from ... import` | AST visitor raises `SandboxSecurityError` |
| `eval`, `exec`, `compile` | AST visitor catches call to forbidden name |
| `open`, `input`, `breakpoint` | AST visitor catches call to forbidden name |
| `getattr`, `setattr`, `delattr` | AST visitor catches call to forbidden name |
| `globals`, `locals`, `vars`, `dir` | AST visitor catches call to forbidden name |
| Dunder attribute access (`__class__`, `__builtins__`, etc.) | AST visitor catches attribute access |
| `global` / `nonlocal` declarations | AST visitor raises `SandboxSecurityError` |
| Network, subprocess, filesystem | No import allowed; no binding injected |

### Timeout

Hard wall-clock limit via daemon thread. If the program does not complete within
`timeout_seconds`, `SandboxTimeoutError` is raised in the calling thread.
The worker thread is a daemon thread; it is abandoned on timeout and reaped when
the process exits.

### Known limitations

1. A timed-out tight loop continues running until process exit (CPython threading
   limitation — no way to forcibly kill a Python thread).
2. Memory limits are not enforced. A malicious program could allocate large objects
   before hitting the timeout. This is acceptable in Phase 1 (sandbox is not for
   adversarial code).
3. CPU-intensive programs will consume cycles on the worker thread even after timeout.
4. The safe builtins list is conservative. It can be extended if specific built-ins
   are needed for future workflows.

---

## DeterministicTaskCompiler

Converts a structured intent dict into a `ProgramExecutionPlan`. No LLM,
no synthesis. Same input always produces the same plan.

### Supported workflows

| Workflow | Input | Output |
|----------|-------|--------|
| `count_lines` | text string | `{line_count, non_empty_line_count, char_count}` |
| `count_words` | text string | `{word_count, line_count, char_count}` |
| `normalize_text` | text string | `{normalized, line_count, char_count}` |
| `word_frequency` | text string | `{top_words, unique_word_count, total_word_count}` |

### Intent dict fields

```python
{
    "workflow": "count_lines",        # required
    "timeout_seconds": 5.0,          # optional, default 5.0
    "top_n": 10,                      # optional (word_frequency only), default 10
}
```

### Fallback behaviour

Unknown or unsupported workflow → `DirectExecutionPlan` (falls back to direct
execution without error). This is the safe default: the system degrades gracefully
rather than failing loudly when it encounters a workflow it doesn't understand.

---

## ProgramExecutor

Accepts a `ProgramExecutionPlan` and returns a structured result dict.

```python
# Success
{"ok": True, "result": <value>, "plan_id": "...", "execution_mode": "program", "duration_seconds": 0.001}

# Failure (fails closed — never falls through to unsafe execution)
{"ok": False, "error": "...", "error_type": "timeout|security|runtime|validation", ...}
```

Error types:
- `validation` — plan is invalid before execution starts
- `security` — AST validator caught a forbidden construct
- `timeout` — program exceeded its wall-clock limit
- `runtime` — program raised an unhandled exception at runtime

---

## Gateway Integration

`ToolRequest` (in `execution_router.py`) accepts two new optional fields:

```python
class ToolRequest(BaseModel):
    plan_type:      str           = "direct"   # "direct" | "program"
    workflow:       Optional[str] = None       # named workflow for compiler
    program_source: Optional[str] = None       # raw program text (takes precedence)
```

When `plan_type == "program"`:
1. If `program_source` is set: use it directly (sandbox will validate it).
2. Else if `workflow` is set: compile via `DeterministicTaskCompiler`.
3. Else: return `{"ok": False, "error_type": "validation"}`.

All policy enforcement is complete **before** `_dispatch_execution` is called.
The World Kernel's verdict is final and is not re-evaluated inside the program path.

### Trace / provenance

The `execution_mode` field in the result dict (`"direct"` or `"program"`) is
included in `result_summary` inside each `TraceEntry`. The existing trace
infrastructure records this without modification.

---

## What Is Intentionally NOT in Phase 1

| Not implemented | Reason |
|-----------------|--------|
| Process-level isolation | Requires container/seccomp design (separate ADR) |
| Memory limits | Requires OS-level resource limits (cgroups/rlimit) |
| `ProgramRegistry` persistence | No storage backend yet |
| Program Ladder (observed/reviewed/attested) | Review workflow not yet specified |
| LLM-generated programs | Explicitly prohibited — no LLM on enforcement path |
| Dynamic policy from programs | Programs never touch the World Kernel |
| `TaskCompiler` invoked at World Kernel level | TaskCompiler is post-enforcement only |
| Multiple language runtimes | Phase 1 is Python-only (language="python") |

---

## Architectural Invariant: No Program Can Expand Permissions

A program executed via `ProgramExecutor` cannot:
- Expand its own allowed bindings
- Re-evaluate policy
- Access the World Kernel
- Modify taint state
- Call `IRBuilder`

The program runs in a namespace that contains **only** what was explicitly injected.
There is no path from the program namespace back to any enforcement component.

---

## Files Added / Modified

### New files

| File | Purpose |
|------|---------|
| `src/agent_hypervisor/program_layer/sandbox_runtime.py` | AST-validated restricted exec() |
| `src/agent_hypervisor/program_layer/task_compiler.py` | Deterministic workflow compiler |
| `tests/program_layer/__init__.py` | Test package |
| `tests/program_layer/test_program_layer.py` | 63 tests |
| `examples/program_layer/dual_execution_demo.py` | Runnable two-mode demo |
| `docs/program_layer_phase1.md` | This document |

### Modified files

| File | Change |
|------|--------|
| `program_layer/execution_plan.py` | Added `language`, `allowed_bindings`, `timeout_seconds`, `metadata` to `ProgramExecutionPlan` |
| `program_layer/program_executor.py` | Replaced `NotImplementedError` stub with real sandbox execution |
| `program_layer/__init__.py` | Added `SandboxRuntime`, `DeterministicTaskCompiler`, error types to public surface |
| `hypervisor/gateway/execution_router.py` | Added `workflow`, `program_source` to `ToolRequest`; implemented `_dispatch_program()` |

---

## Running the Demo

```bash
python examples/program_layer/dual_execution_demo.py
```

Expected output shows:
1. Direct execution (word count via tool adapter)
2. Program execution via compiled workflow (word frequency)
3. Program execution via raw program_source (line count)
4. Sandbox blocking forbidden operations (import, eval, open, infinite loop)
5. Architectural note separating World Kernel from Program Layer

## Running the Tests

```bash
pytest tests/program_layer/test_program_layer.py -v
```

63 tests, covering all specified requirements.
