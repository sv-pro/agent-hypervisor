# Script Notes

## Core constraints

- Do not claim that agent intent is solved.
- Do not claim semantic safety in general.
- Emphasize that this is a bounded, workflow-specific deterministic policy architecture.
- Keep returning to one sentence: observed execution can be compiled into runtime boundaries.
- Contrast reactive filtering with declarative world definition.
- Use "bounded autonomy" as the positive framing.
- Treat scope creep as the operational failure mode and manifest compilation as the response.

## Key concepts to introduce clearly

- **Bootstrap trust model**: the system starts with built-in source trust defaults (`repo_local: trusted`, `environment: untrusted`, `llm_output: untrusted`, `tool_output: conditional`). The user does not begin by writing a trust model. This is the starting point.
- **Taint derivation**: taint is derived from input source provenance and propagated through `depends_on` execution dependencies. It is not manually assigned. "Taint is a deterministic function of provenance and flow."
- **Safe compression**: the manifest may compress observed behavior, but must not introduce capabilities absent from the safe trace. "You can lose precision, but you cannot add new capabilities."
- **Value of derivation**: the value is not just that a manifest exists, but that it can be derived from evidence rather than guessed.

## Lines to work in naturally

> "This PoC does not try to make agent reasoning safe; it makes the executable boundary around agent actions explicit, minimal, and reproducible."

> "Taint is a deterministic function of provenance and flow."

> "You can lose precision, but you cannot add new capabilities."

> "The value is not just that a manifest exists, but that it can be derived from evidence rather than guessed."

## Terminology to use consistently

- **tracer** / **TraceRecorder**: records execution (Stage 0)
- **profiler**: reads traces and derives a capability profile (Stage 1)
- **capability profile**: the minimal (tool, action, resource) set derived from benign execution
- **manifest compiler**: translates the profile into a manifest (Stage 2)
- **World Manifest**: the declarative policy document
- **policy engine** / **enforcement engine**: evaluates steps against the manifest (Stage 3)
- **bootstrap trust model**: the built-in source trust defaults
- **taint**: provenance-derived, not annotated

Do not conflate tracer and profiler. The tracer records; the profiler derives.

## What to avoid

- Do not say users start by writing a trust model.
- Do not say taint is manually set.
- Do not claim the current manifest fully preserves fine-grained `(tool, action, resource)` triple semantics — the current PoC collapses some of this structure.
- Do not say the system eliminates all unsafe behavior.
- Do not invoke "Agent Hypervisor" framing; this PoC does not implement a hypervisor layer.
