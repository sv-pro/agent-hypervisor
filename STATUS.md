# STATUS.md — Agent Hypervisor

*Component maturity model. Updated: March 2026.*

This document describes the maturity and classification of every major component in the Agent Hypervisor repository. Use it to understand what is production-ready, what is in progress, what is experimental, and what is archived.

---

## Maturity Classification

| Symbol | Label | Meaning |
|--------|-------|---------|
| ✅ | **Canonical** | Stable, well-defined, authoritative. Production-quality or publication-ready. |
| 🔵 | **Supported** | Working, actively maintained, but not yet canonical. May evolve. |
| 🟡 | **Experimental** | Proof-of-concept or draft quality. May have gaps or rough edges. Not relied on by other components. |
| 🟠 | **In Progress** | Being actively developed toward a higher maturity level. |
| ⬜ | **Planned** | Not yet implemented. Specified in the roadmap. |
| 🗄️ | **Archived** | Superseded or obsolete. Preserved for historical reference; not maintained. |

---

## Architecture Documentation

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Architectural thesis | ✅ Canonical | `CONCEPT.md` | Shortest serious explainer |
| Full whitepaper | ✅ Canonical | `docs/WHITEPAPER.md` | Complete formal argument |
| 12-Factor Agent standard | ✅ Canonical | `12-FACTOR-AGENT.md` | Evaluation checklist |
| Threat model | ✅ Canonical | `THREAT_MODEL.md` | Formal scope, attack surface |
| FAQ / objection handling | ✅ Canonical | `FAQ.md` | Hard objections answered |
| Positioning / scope | ✅ Canonical | `POSITIONING.md` | What this is and is not |
| Architecture spec | ✅ Canonical | `docs/ARCHITECTURE.md` | Implementation-oriented |
| Technical specification | ✅ Canonical | `docs/TECHNICAL_SPEC.md` | Deterministic physics engine |
| Glossary | ✅ Canonical | `docs/GLOSSARY.md` | Authoritative term definitions |
| Evaluation framework | ✅ Canonical | `docs/EVALUATION_FRAMEWORK.md` | Crutch/Workaround/Bridge lens |
| Perception-bounded world | ✅ Canonical | `docs/concepts/perception_bounded_world.md` | Theoretical foundation |
| Capability rendering | 🔵 Supported | `docs/concepts/capability_rendering.md` | Construction vs. filtering |
| VS existing solutions | ✅ Canonical | `docs/VS_EXISTING_SOLUTIONS.md` | Guardrails, sandboxes, policy engines |
| Vulnerability case studies | ✅ Canonical | `docs/VULNERABILITY_CASE_STUDIES.md` | Architecturally predictable failures |
| Roadmap | 🔵 Supported | `ROADMAP.md` | Development stages and versioned plans |
| ADR-001 — Manifest versioning | 🟡 Open | `docs/ADR/ADR-001-manifest-schema-versioning.md` | Decision pending v0.2 |
| ADR-002 — Simulate fidelity | 🟡 Open | `docs/ADR/ADR-002-ahc-simulate-fidelity.md` | Decision pending v0.3 |
| ADR-003 — Policy IR stability | 🟡 Open | `docs/ADR/ADR-003-policy-ir-stability.md` | Decision pending v0.4 |
| ADR-004 — Policy language | 🟡 Open | `docs/ADR/ADR-004-policy-language-backend.md` | Decision pending v0.4 |

---

## Publication Series — *The Missing Layer*

| Article | Status | Location |
|---------|--------|----------|
| 01 — The Pattern | ✅ Published | `docs/pub/the-missing-layer/01-the-pattern/` |
| 02 — AI Aikido | ✅ Published | `docs/pub/the-missing-layer/02-ai-aikido/` |
| 03 — Design-Time HITL | ✅ Published | `docs/pub/the-missing-layer/03-design-time-hitl/` |
| 04 — MCP as Missing Layer | ✅ Published | `docs/pub/the-missing-layer/04-mcp-missing-layer/` |
| 05 — World Manifest | ⬜ Planned | — |
| 06 — Policy Engine | ⬜ Planned | — |
| 07 — Benchmark | ⬜ Planned | — |
| Taint series (3 articles) | ⬜ Planned | — |

---

## Implementation — Layer Coverage

### Layer 0: Execution Physics

| What | Status | Notes |
|------|--------|-------|
| Container / network isolation | ⬜ Planned | Architectural spec only; `Dockerfile` exists but not the isolation layer |
| OS-level sandboxing (seccomp etc.) | ⬜ Planned | Out of scope for current PoC |

### Layer 1: Base Ontology (World Manifest + Compiler)

| What | Status | Location | Notes |
|------|--------|----------|-------|
| World Manifest schema v1 | ✅ Canonical | `src/compiler/schema.py` + `manifests/` | Defined and used |
| Manifest loader | ✅ Canonical | `src/compiler/manifest.py` | |
| Capability profiler | ✅ Canonical | `src/compiler/profile.py` | Derive minimal capability set from traces |
| Capability renderer | ✅ Canonical | `src/compiler/render.py` | Manifest → capability surface |
| `awc` CLI | ✅ Canonical | `src/compiler/cli.py` | `awc run`, `awc compile`, `awc profile`, `awc render` |
| Enforcer (ABSENT/POLICY) | ✅ Canonical | `src/compiler/enforcer.py` | Deterministic ALLOW/DENY |
| World Manifest schema v2 | ⬜ Planned v0.2 | — | Entity, Actor, DataClass, TrustZone types |
| `ahc validate` | ⬜ Planned v0.3 | — | Schema-level validation CLI |
| `ahc simulate` | ⬜ Planned v0.3 | — | Dry-run scenario against manifest |
| `ahc diff` | ⬜ Planned v0.3 | — | Structural manifest diff |
| `ahc coverage` | ⬜ Planned v0.3 | — | Which manifest rules were exercised |
| `ahc tune` | ⬜ Planned v0.3 | — | Suggest manifest edits from failing scenarios |
| `ahc draft` (LLM-assisted) | ⬜ Planned v0.3 | — | Design-time LLM authoring |

### Layer 2: Dynamic Ontology Projection

| What | Status | Location | Notes |
|------|--------|----------|-------|
| Capability DSL (YAML) | 🔵 Supported | `src/authoring/capabilities/` | models, parser, validator |
| Named policy presets (worlds) | 🔵 Supported | `src/authoring/worlds/` | `base`, `email_safe` |
| MCP integration wrapper | 🔵 Supported | `src/authoring/integrations/mcp/` | Thin ProxyMCPServer |
| Audit/event logger | 🔵 Supported | `src/authoring/audit/` | One-line JSON event logger |
| Dynamic context projection | 🟠 In Progress | — | Role/state-based capability scoping |

### Layer 3: Execution Governance

| What | Status | Location | Notes |
|------|--------|----------|-------|
| `build_runtime()` factory | ✅ Canonical | `src/runtime/runtime.py` | Single entry point |
| `IRBuilder.build()` | ✅ Canonical | `src/runtime/ir.py` | Construction-time enforcement |
| `TaintContext` | ✅ Canonical | `src/runtime/taint.py` | Monotonic taint propagation |
| `SafeMCPProxy` | ✅ Canonical | `src/runtime/proxy.py` | In-path enforcement layer |
| `Executor` / `Sandbox` | ✅ Canonical | `src/runtime/executor.py` | Executes validated IntentIR |
| `Channel` / source identity | ✅ Canonical | `src/runtime/channel.py` | Trust level resolution |
| `compile_world()` | ✅ Canonical | `src/runtime/compile.py` | Manifest → CompiledPolicy |
| Provenance tracking | 🔵 Supported | `src/hypervisor/` + `src/runtime/` | Full chain not yet unified |
| Approval gate | 🟡 Experimental | `src/runtime/` | `ApprovalRequired` raised; not yet resolved |
| Budget enforcement | 🔵 Supported | `src/hypervisor/` | Cumulative state limits |
| Reversibility classification | 🟠 In Progress | — | M2/M4 deliverable |
| Audit log (immutable) | 🔵 Supported | `src/authoring/audit/` | One-line JSON; not yet hardened |

---

## Implementation — PoC and Hypervisor Core

| What | Status | Location | Notes |
|------|--------|----------|-------|
| Hypervisor PoC core | 🔵 Supported | `src/hypervisor.py` | ~200 line PoC integrating all layers |
| Agent stub | 🔵 Supported | `src/agent_stub.py` | Test agent for PoC scenarios |
| Policy modules | 🔵 Supported | `src/policy/` | |
| Semantic layer | 🔵 Supported | `src/semantic/` | |
| Boundary layer | 🔵 Supported | `src/boundary/` | |
| Compiler modules | 🔵 Supported | `src/compiler/` (hypervisor compiler, distinct from awc) | |
| Gateway | 🔵 Supported | `src/gateway/` | |
| Provenance | 🔵 Supported | `src/provenance/` | |

---

## Examples and Demos

| What | Status | Location | Notes |
|------|--------|----------|-------|
| Basic PoC demo | ✅ Canonical | `examples/basic/` | `01_simple_demo.py` and variants |
| Showcase demo | ✅ Canonical | `examples/showcase/` | `scripts/run_showcase_demo.py` |
| Semantic examples | 🔵 Supported | `examples/semantic/` | |
| Provenance firewall demo | 🔵 Supported | `examples/provenance_firewall/` | |
| Workarounds examples | 🔵 Supported | `examples/workarounds/` | |
| Comparisons | 🔵 Supported | `examples/comparisons/` | |
| Compiler scenarios | ✅ Canonical | `examples/compiler/` | safe, unsafe, retry, zombie |
| Authoring quickstart | 🔵 Supported | `examples/authoring/` | Capability authoring from scratch |
| Playground (React/TS) | ✅ Published | `demos/playground/` | Interactive world virtualization visualizer |
| Core presentation deck | ✅ Published | `demos/presentation-core/` | The Missing Layer narrative |
| Enterprise deck | ✅ Published | `demos/presentation-enterprise/` | Capability rendering as infrastructure |
| FAQ deck | ✅ Published | `demos/presentation-faq/` | Objection handling |

---

## Research

| What | Status | Location | Notes |
|------|--------|----------|-------|
| AgentDojo benchmark integration | 🟠 In Progress | `research/agentdojo-bench/` | Running; M4 deliverable |
| Benchmark scenario taxonomy | 🔵 Supported | `research/benchmarks/` | attack / safe / ambiguous classification |
| Attack containment metrics | 🟠 In Progress | `research/reports/` | Being generated from AgentDojo runs |
| Benchmark traces | 🔵 Supported | `research/traces/` | Execution traces for replay |

---

## Lab (Experimental / Historical)

| What | Status | Location | Notes |
|------|--------|----------|-------|
| Compiler PoC (v0) | 🗄️ Archived | `lab/compiler-poc/` | Historical precursor to `src/compiler/`; not maintained |
| Compiler PoC notebooks | 🟡 Experimental | `lab/compiler-poc/notebooks/` | Jupyter experiments; useful for ML track research |
| Summit / presentation drafts | 🟡 Experimental | `lab/compiler-poc/docs/summit/` | Panel drafts; may be published separately |

---

## Infrastructure

| What | Status | Notes |
|------|--------|-------|
| `Dockerfile` | 🔵 Supported | Basic container; not hardened for production |
| `docker-compose.yml` | 🔵 Supported | Local demo stack |
| `pyproject.toml` | 🔵 Supported | Unified; install with `pip install -e .` |
| CI (GitHub Actions) | 🔵 Supported | `tests/` coverage |

---

*See [ROADMAP.md](ROADMAP.md) for the full development plan.*  
*See [CONCEPT.md](CONCEPT.md) for the architectural overview.*  
*See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the implementation specification.*
