# CLAUDE.md — Agent Hypervisor

This file provides guidance for AI assistants (Claude Code and similar) working in this repository.

---

## Project Overview

**Agent Hypervisor** is a deterministic execution governance layer for AI agents. It enforces semantic-level isolation through ontological boundaries rather than probabilistic filtering — safety is achieved by removing possibilities at compile time, not by monitoring at runtime.

The core thesis: AI agent security should be addressed at the architecture level through deterministic enforcement, not probabilistic guardrails.

**Current version**: 0.2.0
**Python requirement**: >=3.10
**Primary language**: Python

---

## Repository Structure

```
agent-hypervisor/
├── src/agent_hypervisor/       # Main package (all production code)
│   ├── runtime/                # Layer 3: Execution governance kernel
│   ├── compiler/               # Layer 1: World Manifest compiler & CLI
│   ├── authoring/              # Layer 2: Capability DSL and policy presets
│   ├── hypervisor/             # Hypervisor PoC, gateway, policy engine
│   ├── program_layer/          # Optional: task compilation & workflow
│   ├── economic/               # Economic constraints (cost/budget enforcement)
│   ├── models.py               # Re-exports hypervisor models
│   └── __init__.py             # Public API exports
├── tests/                      # Test suite (mirrors src structure)
│   ├── runtime/                # Runtime invariant, determinism, proxy tests
│   ├── compiler/               # Compiler tests
│   ├── authoring/              # Authoring layer tests
│   └── program_layer/          # Program layer tests
├── docs/                       # Architecture docs, whitepapers, ADRs
│   ├── concept/                # Core concepts (start with overview.md)
│   ├── architecture/           # Whitepaper, threat model, ADRs
│   ├── pub/                    # Published article series
│   └── adr/                    # Architecture Decision Records
├── examples/                   # Runnable demonstrations
│   ├── basic/                  # Simple demos (start here)
│   ├── runtime/                # Provenance firewall, semantic examples
│   ├── claude_like_runtime/    # Full working example
│   └── compiler/               # Compiler workflow examples
├── research/                   # AgentDojo benchmarks, traces, reports
├── demos/                      # Presentation decks, interactive playground
├── archive/                    # Historical experimental code (do not modify)
├── lab/                        # Archived PoC notebooks (do not modify)
├── experiments/                # Research experiments (DSPy, etc.)
├── pyproject.toml              # Project config, dependencies, test config
├── requirements.txt            # Base dependencies
├── conftest.py                 # Pytest root configuration
├── Dockerfile                  # Container definition
└── docker-compose.yml          # Local demo stack
```

---

## Architecture: Four Layers

The system is organized into four deterministic layers:

| Layer | Name | Location | Purpose |
|-------|------|----------|---------|
| 0 | Execution Physics | (planned) | Container/network isolation |
| 1 | Base Ontology | `compiler/` | World Manifest schema & compiler |
| 2 | Dynamic Ontology | `authoring/` | Capability DSL & policy presets |
| 3 | Execution Governance | `runtime/` | IRBuilder, taint, provenance, approvals |

**Execution flow**:
```
world_manifest.yaml
    ↓
compile_world() [runtime/runtime.py]
    ↓
CompiledPolicy (frozen, metadata only)
    ↓
Channel → IRBuilder → Executor → worker subprocess
```

### Core Safety Mechanisms

- **IntentIR** (`runtime/ir.py`) — Sealed object; cannot be constructed outside `IRBuilder`. No external code can inject an execution intent.
- **IRBuilder.build()** (`runtime/ir.py`) — All constraints checked at construction time, before any execution begins.
- **TaintedValue** (`runtime/taint.py`) — Every value that passes through execution is tainted. Taint is monotonically joined; it can never be removed.
- **Process boundary** (`runtime/worker.py`) — Handlers run in a separate subprocess; policy evaluation runs in the main process. Neither can see the other's internals.
- **SafeMCPProxy** (`runtime/proxy.py`) — In-path enforcement for all MCP tool calls.

---

## Development Setup

```bash
# Install in development mode
pip install -e .

# Or install dependencies directly
pip install pyyaml pytest fastapi uvicorn
```

**Python version**: 3.10+ (see `.python-version`)

---

## Running Tests

```bash
# Run all tests
pytest

# Run specific layer tests
pytest tests/runtime/
pytest tests/compiler/
pytest tests/authoring/
pytest tests/program_layer/

# Verbose output
pytest -v

# Run a specific test file
pytest tests/runtime/test_invariants.py
```

**Test configuration** is in `pyproject.toml` under `[tool.pytest.ini_options]`:
- `testpaths = ["tests"]`
- `pythonpath = ["src/agent_hypervisor"]`

Tests cover: invariants, determinism, proxy enforcement, provenance firewall, approval workflows, policy engine evaluation.

---

## CLI Tools

Two CLI entry points are installed (both map to the same `compiler/cli.py`):
- `awc` — Agent World Compiler
- `ahc` — Agent Hypervisor Compiler

```bash
# Run a scenario
awc run --scenario safe
awc run --scenario unsafe --compare
awc run --scenario zombie

# Compile a manifest
awc compile --manifest path/to/manifest.yaml

# Profile from an execution trace
awc profile --trace path/to/trace.json

# Render capability surface
awc render --manifest path/to/manifest.yaml
```

---

## Running Examples

```bash
# Basic demo (7 scenarios)
python examples/basic/01_simple_demo.py

# Provenance firewall demo (unprotected / protected / trusted modes)
python examples/runtime/provenance_firewall/demo.py

# Full claude-like runtime example
python examples/claude_like_runtime/main.py
```

---

## Docker

```bash
# Start local demo stack
docker-compose up

# Build image
docker build -t agent-hypervisor .
```

---

## Key Conventions

### Code Style

- No LLM on the execution path — compile-time decisions only; runtime is deterministic.
- Enforce at construction time, not at call time. If something is invalid, reject it in `IRBuilder.build()`, not in `Executor.run()`.
- Taint is never dropped. Any code that removes or bypasses taint propagation is a security regression.
- Policy objects are frozen after compilation. `CompiledPolicy` is immutable once created.
- Process boundary is a hard invariant. Handler code must never have direct access to policy state.

### Module Responsibilities

- `runtime/` — No I/O except subprocess dispatch. No LLM calls. No mutable shared state.
- `compiler/` — Pure transformation: YAML → deterministic policy artifacts. CLI wrappers only.
- `authoring/` — Design-time only. Defines what is possible; does not execute anything.
- `hypervisor/` — PoC-quality gateway and policy engine. Not production hardened.
- `economic/` — First-class budget enforcement. Cost decisions happen at IR construction, not post-hoc.

### File Naming

- Source modules use `snake_case.py`
- Test files are prefixed `test_` and mirror the source path
- YAML manifests are `snake_case.yaml`
- ADRs are numbered: `docs/adr/ADR-NNN-title.md`

### Git Workflow

- `master` — Stable releases
- `dev` — Integration branch for completed features
- Feature branches: `claude/<feature-name>-<id>` (AI) or descriptive names (human)
- PRs merge into `dev`; `dev` merges into `master` for releases

---

## Component Maturity

| Status | Meaning |
|--------|---------|
| ✅ Canonical | Production-ready, stable API |
| 🔵 Supported | Working and maintained, may evolve |
| 🟠 In Progress | Under active development |
| ⬜ Planned | Designed but not implemented |
| 🗄️ Archived | Historical; do not modify |

**Canonical (stable API, do not break)**:
- World Manifest schema v1, manifest loader
- `IRBuilder`, `TaintContext`, `SafeMCPProxy`, `Executor`, `Channel`
- Capability profiler, renderer, enforcer
- `awc` CLI commands
- Audit logger
- Core test suite

**Supported (may evolve)**:
- Capability DSL, named policy presets
- MCP integration wrapper
- Hypervisor PoC and gateway
- Economic constraints
- Program layer

**Do not modify**:
- `archive/` — Historical experimental code
- `lab/` — Archived PoC notebooks

---

## Documentation Map

| Question | Document |
|----------|----------|
| What is this? | `docs/concept/overview.md` |
| Core concepts | `docs/concept/concepts.md` |
| Full architecture | `docs/architecture/whitepaper.md` |
| Threat model | `docs/architecture/threat-model.md` |
| vs. other solutions | `docs/research/vs-existing-solutions.md` |
| How to write a manifest | `docs/architecture/hello-world.md` |
| ADRs (design decisions) | `docs/adr/` |
| Published articles | `docs/pub/the-missing-layer/` |
| Changelog | `CHANGELOG.md` |
| Roadmap | `ROADMAP.md` |
| Component maturity | `STATUS.md` |

---

## Important Patterns to Follow

### When Adding a New Runtime Feature

1. Define domain models in `runtime/models.py`
2. Add IR-level constraint in `runtime/ir.py` (checked in `IRBuilder.build()`)
3. Implement enforcement in `runtime/executor.py` or `runtime/proxy.py`
4. Add taint propagation in `runtime/taint.py` if the feature touches data flow
5. Write invariant tests in `tests/runtime/test_invariants.py`
6. Write determinism tests in `tests/runtime/test_determinism.py`

### When Adding a New Compiler Feature

1. Update schema in `compiler/schema.py`
2. Update loader in `compiler/loader.py`
3. Update enforcer in `compiler/enforcer.py` for ALLOW/DENY decisions
4. Add CLI command in `compiler/cli.py` if user-facing
5. Add tests in `tests/compiler/`

### When Adding Examples

- Place in `examples/` with a clear subdirectory name
- Examples must be runnable with a simple `python examples/*/main.py`
- Include a brief docstring at the top explaining what the example demonstrates
- Do not add examples to `archive/` or `lab/`

### When Writing Tests

- Test safety invariants explicitly (not just happy paths)
- Use `conftest.py` for shared fixtures
- Name tests descriptively: `test_taint_cannot_be_dropped`, `test_ir_rejects_unknown_tool`
- Tests for security properties go in `test_invariants.py`, not general test files

---

## What NOT to Do

- Do not add LLM calls to the execution path (`runtime/`). LLMs belong at compile time or in the `authoring/` layer.
- Do not add mutable shared state to runtime modules.
- Do not bypass the `IRBuilder` to construct `IntentIR` directly — the seal is a security invariant.
- Do not remove or weaken taint propagation without an ADR.
- Do not modify `archive/` or `lab/` directories.
- Do not add probabilistic filtering ("check if this looks safe") to the runtime layer — use deterministic constraints.
- Do not add backwards-compatibility shims unless explicitly required; prefer clean API changes with updated callers.
