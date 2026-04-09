# Wiki Log

## [2026-04-09] ingest | Ingested Python source code under src/

Read all Python modules in `src/core/` and `src/agent_hypervisor/` (7 sub-packages, ~60 modules). Synthesized package-level and module-level wiki articles, and updated `PROMPT.txt` to include a formal Python code integration schema.

Updated:
- `wiki/PROMPT.txt` — added "Python Code as a Source" section with package-level and module-level article schema, deep-link convention, and code ingest workflow.
- `wiki/index.md` — added "Code Documentation" section with package and module deep-dive links.

Created package-level articles (one per package):
- `wiki/code/index.md` — package map, module index, architectural pattern table
- `wiki/code/agent_hypervisor.md` — top-level public API
- `wiki/code/runtime.md` — Layer 3 Execution Governance kernel
- `wiki/code/compiler.md` — Layer 1 Base Ontology compiler & CLI
- `wiki/code/authoring.md` — Layer 2 Dynamic Ontology (Capability DSL, World presets)
- `wiki/code/hypervisor.md` — PoC Gateway (HTTP server, PolicyEngine, approval workflow)
- `wiki/code/economic.md` — Economic constraints (budget enforcement, cost estimation)
- `wiki/code/program_layer.md` — Optional execution abstraction (sandbox runtime)
- `wiki/code/core.md` — Portable reference implementation

Created module deep-dive articles (for security-critical modules):
- `wiki/code/modules/ir.md` — IntentIR & IRBuilder; construction-time enforcement; sealing
- `wiki/code/modules/taint.md` — TaintedValue & TaintContext; monotonic lattice; propagation model
- `wiki/code/modules/compile.md` — compile_world() & CompiledPolicy; immutability; O(1) capability matrix
- `wiki/code/modules/channel.md` — Channel & Source; sealed trust derivation; fail-closed defaults
- `wiki/code/modules/proxy.md` — SafeMCPProxy; single enforcement point; typed denial kinds
- `wiki/code/modules/executor.md` — Executor; subprocess boundary; SimulationExecutor; worker registry agreement
- `wiki/code/modules/firewall.md` — ProvenanceFirewall; RULE-01 through RULE-05; ValueRef provenance model
- `wiki/code/modules/core_hypervisor.md` — ManifestResolver; physics laws; input sanitization; determinism

## [2026-04-09] ingest | Ingested ZombieAgent Scenario
Processed `scenarios/zombie-agent/SCENARIO.md` and `manifest.yaml` to extract the core attack flow and structural mitigations. Created `wiki/scenarios/zombie-agent.md` and initialized the wiki index.

## [2026-04-09] ingest | Ingested Core Repository
Synthesized the core philosophical concepts of the project sourced from `WHITEPAPER.md`, `README.md`, and `GLOSSARY.md`. Segmented structured knowledge into a "clean" space involving categories around `concepts/` and `comparisons/`. 

Also initialized the `_research/` space acting as a messy staging ground outlining ongoing/archive experiments derived from the local `_research/` directory.

Created:
- `wiki/concepts/architecture.md`
- `wiki/concepts/ai-aikido.md`
- `wiki/concepts/world-manifest.md`
- `wiki/concepts/trust-and-taint.md`
- `wiki/concepts/manifest-resolution.md`
- `wiki/comparisons/agent-hypervisor-vs-camel.md`
- `wiki/_research/index.md`
- Vastly expanded `wiki/index.md`.

## [2026-04-09] update | Indexed Wiki Directories
Created summary index files for concepts, comparisons, and scenarios. Deep-linked existing docs to their respective raw source code files in src/ according to the updated PROMPT.txt schema.

## [2026-04-09] update | Codebase Architectural Split
Synthesized the conceptual differences separating the minimal pure `src/core` logic codebase against the fully heavy `src/agent_hypervisor` framework codebase into `concepts/codebase-analysis.md`.

### 04-09-2026: Agent Hypervisor Gateway Shadow Mode
- Refactored `ExecutionRouter` in `agent_hypervisor/hypervisor/gateway/execution_router.py` to use `CoreDecisionAdapter`.
- Staged shadow migration of legacy `ProvenanceFirewall` and `PolicyEngine` alongside `core.hypervisor` resolution logic.
- Fixed python module import masking related to `provenance` directory vs `provenance.py`.
