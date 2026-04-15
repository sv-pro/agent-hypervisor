---
name: run-tests
description: Run the Agent Hypervisor test suite or a specific layer
argument-hint: "[runtime|compiler|authoring|program_layer|all]"
---

Run Agent Hypervisor tests for: $ARGUMENTS

Choose the matching pytest command:

- `runtime` → `pytest tests/runtime/ -v`
- `compiler` → `pytest tests/compiler/ -v`
- `authoring` → `pytest tests/authoring/ -v`
- `program_layer` → `pytest tests/program_layer/ -v`
- `all` or no argument → `pytest -v`

**Import path note**: `pyproject.toml` sets `pythonpath = ["src/agent_hypervisor"]`.
Tests import submodules directly — e.g. `from runtime.ir import IRBuilder` — not
via the package root. Do not change this without updating all test imports.

For security invariant tests specifically: `pytest tests/runtime/test_invariants.py -v`
For determinism tests: `pytest tests/runtime/test_determinism.py -v`
