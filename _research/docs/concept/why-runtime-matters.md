# Why this matters

One level deeper than the README.

---

## Why ontology is different from permission checks

A permission check assumes the action already exists as a representable request. Safety happens at interception: the request is formed, a policy evaluates it, and the system allows or denies.

This runtime moves the boundary earlier. An action not declared in `world_manifest.yaml` cannot be represented as an `IntentIR`. There is no object to intercept. `IRBuilder.build()` raises `ConstructionError` before any execution structure is created.

This is not a semantic difference — it is structural. A policy engine says "this request is denied." This runtime says "this request cannot be formed." The difference matters when you are reasoning about what an agent system *can do*, not just what it is *allowed to do*.

Taint follows the same logic. A taint check at execution time means: the request exists, it carries a tag, the executor examines the tag and decides. Here, tainted data flowing into an external action fails at `IRBuilder.build()`. The `ExecutionSpec` is never created. There is no decision point to bypass.

---

## Why the subprocess boundary matters

The main process holds no handler functions. `Executor` is a transport: it serializes an `ExecutionSpec` (action name + params), sends it to `worker.py` via stdin, and reads a JSON response from stdout.

This means:

- Handler code runs in a separate process address space
- The policy objects, taint state, and `CompiledPolicy` are not in the worker's scope
- The worker has its own closed registry — unknown action names fail there independently
- The boundary is explicit and auditable: exactly one type crosses it (`ExecutionSpec`)

This is not OS-level isolation. The worker inherits the parent's environment. But the architectural separation is real and inspectable: you can read `executor.py` and see exactly what crosses the boundary, and you can see that policy and execution are structurally separated — not just logically separated by convention.

In a hardened deployment, this subprocess seam is the natural place to substitute a container, a gVisor-isolated worker, a remote execution target, or a signed binary.

---

## Why this repo is still only a core

This repo demonstrates the runtime model: ontological construction, taint propagation, subprocess boundary. It does not implement:

- OS-level isolation (seccomp, namespaces, containers)
- Dynamic world shaping (per-session manifest slices)
- Approval workflows for `approval_required` actions
- Audit logs or provenance tracking
- Signing or integrity verification of worker artifacts

These are real requirements for a production agent runtime. They are not here because the goal is to make the core model legible, not to build a product.

The claim this repo makes is narrow: **if you build on this model, certain classes of mistake become structurally impossible.** Unknown actions cannot be constructed. Tainted data cannot reach external actions. The execution boundary is enforced by process separation, not by convention.

Whether that is sufficient for your threat model depends on what you are building.
