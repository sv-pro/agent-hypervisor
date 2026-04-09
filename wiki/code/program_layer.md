# Package: `program_layer`

**Source:** [`src/agent_hypervisor/program_layer/`](../../src/agent_hypervisor/program_layer/)

The `program_layer` package is an **optional execution abstraction** that sits *after* all policy enforcement. It decides *how* to execute within an already-approved policy boundary — not *what* is permitted.

**Key invariant:** All policy enforcement (IRBuilder, ProvenanceFirewall, PolicyEngine) completes before the program layer is ever reached. The program layer never re-evaluates policy.

## Public API (`__init__.py`)

| Symbol | Type | Description |
|---|---|---|
| `ExecutionPlan` | abstract class | Base for execution plans (frozen/immutable) |
| `DirectExecutionPlan` | class | Default plan wrapping existing direct execution |
| `ProgramExecutionPlan` | class | Backed by structured program running in sandbox |
| `ProgramExecutor` | class | Runs `ProgramExecutionPlan` in sandbox |
| `SandboxRuntime` | class | Restricted execution environment |
| `DeterministicTaskCompiler` | class | Phase 1 task compilation |
| `SandboxError` | exception | Base sandbox error |
| `SandboxSecurityError` | exception | Violates sandbox policy |
| `SandboxTimeoutError` | exception | Exceeds wall-clock timeout |
| `SandboxRuntimeError` | exception | Unhandled exception at sandbox runtime |

## Modules

| Module | Key Symbols | Description |
|---|---|---|
| `execution_plan.py` | `ExecutionPlan`, `DirectExecutionPlan`, `ProgramExecutionPlan` | Plan type hierarchy |
| `sandbox_runtime.py` | `SandboxRuntime` | Minimal restricted execution environment |
| `program_executor.py` | `ProgramExecutor` | Runs programs in sandbox |
| `task_compiler.py` | `DeterministicTaskCompiler` | Compiles tasks to execution plans |
| `interfaces.py` | `Executor` protocol | Protocol definition for executor implementations |

## Execution Plan Types

```
IRBuilder.build() → IntentIR  ←  all policy checks complete here
    ↓  verdict == allow
ExecutionPlan dispatch
    ├── DirectExecutionPlan  → tool_def.adapter(raw_args)     [default]
    └── ProgramExecutionPlan → ProgramExecutor.execute(plan)   [structured program]
```

**`DirectExecutionPlan`** — identical to prior behavior. Wraps direct tool adapter invocation.

**`ProgramExecutionPlan`** — executes a structured program source inside `SandboxRuntime`. Fields:
- `plan_id` — unique identifier
- `program_source` — Python source code to execute (optional; mutually exclusive with `program_id`)
- `program_id` — reference to a pre-registered program
- `language` — always `"python"` in Phase 1
- `allowed_bindings` — tuple of binding names injected into sandbox
- `timeout_seconds` — wall-clock limit (default 5.0s)

## SandboxRuntime

`SandboxRuntime` is a minimal restricted Python environment:

**Allowed:**
- Safe built-in types: `bool`, `bytes`, `dict`, `float`, `frozenset`, `int`, `list`, `set`, `str`, `tuple`
- Math, string, iteration, introspection builtins (see whitelist)
- Injected bindings: `read_input()`, `emit_result()`, `json_dumps()`, `json_loads()`
- Arithmetic, conditionals, loops, list/dict comprehensions

**Forbidden (raises `SandboxSecurityError`):**
- Any `import` statement
- `eval`, `exec`, `compile`
- `open`, `input`, `breakpoint`
- `getattr`, `setattr`, `delattr`, `vars`, `dir`, `globals`, `locals`
- Dunder attribute access
- Subprocesses, network calls, filesystem access
- Execution beyond `timeout_seconds` (raises `SandboxTimeoutError`)

**AST validation** runs before `exec()` — forbidden patterns are caught before any code runs.

## ProgramExecutor Result Shape

Success:
```json
{
  "ok": true,
  "result": <value from emit_result()>,
  "plan_id": "prog-count_words-abc123",
  "execution_mode": "program",
  "duration_seconds": 0.0023
}
```

Failure:
```json
{
  "ok": false,
  "error": "program exceeded timeout of 5.0s",
  "error_type": "timeout",
  "plan_id": "prog-...",
  "execution_mode": "program",
  "duration_seconds": 5.001
}
```

Error types: `"timeout"`, `"security"`, `"runtime"`, `"validation"`.

## Invariants

1. **Policy enforcement is complete before this layer.** The program layer never makes allow/deny decisions.
2. **Fail closed.** Unknown error → `SandboxError`; exceeds timeout → `SandboxTimeoutError`; forbidden AST node → `SandboxSecurityError`.
3. **Offline by default.** No network, subprocess, or filesystem access permitted in sandbox.
4. **Explicit bindings only.** The sandbox environment contains only what `allowed_bindings` declares.

## See Also

- [Runtime package](runtime.md) — policy enforcement that precedes this layer
- [IRBuilder module](modules/ir.md) — where approval is granted before reaching program layer
- [Four-Layer Architecture](../concepts/architecture.md)
