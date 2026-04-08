# Wiki Log

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
