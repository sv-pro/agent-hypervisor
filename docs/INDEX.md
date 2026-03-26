# Documentation Index

Complete map of Agent Hypervisor documentation, organized by type and purpose.

---

## Canonical Concept Documents

The authoritative statements of the architecture. Start here for any deep engagement.

| Document | Summary | Length |
|---|---|---|
| [../CONCEPT.md](../CONCEPT.md) | Shortest serious explainer of the thesis: the problem, the five-layer model, architectural invariants, honest weaknesses, and open questions | 15 min |
| [WHITEPAPER.md](WHITEPAPER.md) | Full architectural argument: origin insight, AI Aikido, semantic gap, four-layer architecture, and resolution strategy | 30 min |
| [../POSITIONING.md](../POSITIONING.md) | What this repository is and is not: four components, explicit non-claims, current objective | 10 min |
| [../FAQ.md](../FAQ.md) | Answers to the hardest objections: guardrails, policy engines, sandboxes, semantic gap, guarantees | 10 min |
| [concepts/perception_bounded_world.md](concepts/perception_bounded_world.md) | Foundational reframing: agents operate in perception-bounded worlds, not the real world. World design vs. guardrails, ontology fit, capability rendering | 15 min |
| [one_pager_perception_world.md](one_pager_perception_world.md) | One-page summary: problem, reframing, solution, key principles | 3 min |

---

## Threat Model & Security Analysis

| Document | Summary |
|---|---|
| [../THREAT_MODEL.md](../THREAT_MODEL.md) | *Canonical threat model.* Virtualization boundary, trust channels, five in-scope threat classes with mitigations and residual risks, out-of-scope items |
| [VULNERABILITY_CASE_STUDIES.md](VULNERABILITY_CASE_STUDIES.md) | Why current vulnerabilities (prompt injection, ZombieAgent, ShadowLeak) are architecturally predictable given raw-reality agent design |
| [VS_EXISTING_SOLUTIONS.md](VS_EXISTING_SOLUTIONS.md) | Structural comparison to guardrails, policy engines, sandboxing, and multi-layer defense |
| [EVALUATION_FRAMEWORK.md](EVALUATION_FRAMEWORK.md) | Crutch / Workaround / Bridge: a classification lens for AI agent security approaches |
| [concepts/perception_bounded_world.md](concepts/perception_bounded_world.md) | Probabilistic vs. deterministic failure, correlated LLM failure modes, delayed failure problem |
| [case_studies/MS_COPILOT_DLP_BYPASS.md](case_studies/MS_COPILOT_DLP_BYPASS.md) | Microsoft Copilot DLP bypass — analysis through the architectural lens |
| [bash_vs_capability_rendering.md](bash_vs_capability_rendering.md) | Why Bash + string permissions fails where capability rendering succeeds: a structural comparison |

---

## Standards & Manifest Ideas

Design-time artifacts and evaluation standards.

| Document | Summary |
|---|---|
| [../12-FACTOR-AGENT.md](../12-FACTOR-AGENT.md) | Evaluation standard for secure agentic systems: 12 factors across perception, world definition, and system guarantees — each with anti-patterns |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Implementation-oriented view of the runtime and compile flow |
| [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) | Deterministic physics engine, code patterns, and invariant proofs |
| [GLOSSARY.md](GLOSSARY.md) | Canonical definitions for all key terms |
| [ADR/](ADR/) | Architectural Decision Records: manifest schema versioning, simulation fidelity, policy IR stability, policy language backend |

---

## Article Drafts

*The Missing Layer* publication series. Each article has a full version and a medium-length version.

| Article | Status | Full | Medium |
|---|---|---|---|
| 01 — The Pattern | Published | [full](pub/the-missing-layer/01-the-pattern/) | [medium](pub/the-missing-layer/01-the-pattern/) |
| 02 — AI Aikido | Published | [full](pub/the-missing-layer/02-ai-aikido/) | [medium](pub/the-missing-layer/02-ai-aikido/) |
| 03 — Design-Time HITL | Published | [full](pub/the-missing-layer/03-design-time-hitl/) | [medium](pub/the-missing-layer/03-design-time-hitl/) |
| 04 — MCP as Missing Layer | Published | [full](pub/the-missing-layer/04-mcp-missing-layer/) | [medium](pub/the-missing-layer/04-mcp-missing-layer/) |
| 05 — World Manifest Spec | Planned | — | — |
| 06 — The Policy Engine | Planned | — | — |
| 07 — Benchmark & Proof | Planned | — | — |

*Taint* series (planned, 3 articles): The Trust Problem, Taint Propagation, Three Laws of Tainted Data.

Full plan: [pub/PUBLICATIONS_PLAN.md](pub/PUBLICATIONS_PLAN.md)

---

## Summit & Talks Materials

| Resource | Format | What it covers |
|---|---|---|
| [../presentation-core/](../presentation-core/) | Reveal.js (13 slides) | Core narrative: The Missing Layer, four-layer model, full system flow |
| [../presentation-enterprise/](../presentation-enterprise/) | Reveal.js | Enterprise pitch: capability rendering as infrastructure |
| [../presentation-faq/](../presentation-faq/) | Reveal.js | Objection-handling: hardest questions with direct answers |
| [../playground/](../playground/) | TypeScript/React web app | Interactive world virtualization demo (offline capable) |

Playground scenarios:

| ID | Name | Demonstrates |
|---|---|---|
| A | ZombieAgent / OpenClaw Case | Canonicalization ≠ trust |
| B | Trust = Channel | Capabilities as physics, not permission lists |
| C | MCP as Virtual Device | Tools as hypervisor grants, not agent possessions |
| D | Simulate, not Execute | Why blocking is the wrong primitive |

---

## Implementation Reference

Documentation for the proof-of-concept codebase. Not the destination — the demonstration.

| Document | Summary |
|---|---|
| [execution_governance.md](execution_governance.md) | Architecture, canonical scenario, threat analysis for Layer 3 |
| [gateway_architecture.md](gateway_architecture.md) | HTTP API, enforcement pipeline, tool registry |
| [policy_engine.md](policy_engine.md) | Declarative rule evaluation: five-check chain, same-input/same-output guarantee |
| [provenance_model.md](provenance_model.md) | Provenance chains, sticky taint, mixed-provenance scenarios |
| [audit_model.md](audit_model.md) | Trace, approval, and policy version record fields |
| [policy_tuner.md](policy_tuner.md) | Governance-time signal detection and policy improvement suggestions |
| [mcp_integration.md](mcp_integration.md) | MCP integration guide |
| [integrations.md](integrations.md) | Python client, MCP, and REST API examples |
| [copilot_git_governance.md](copilot_git_governance.md) | GitHub Copilot Git governance scenario walkthrough |
| [HELLO_WORLD.md](HELLO_WORLD.md) | 10-minute tutorial |
| [QUICKSTART.md](QUICKSTART.md) | Getting started guide |
| [PROOF_PACKAGE.md](PROOF_PACKAGE.md) | Proof artifacts and benchmark package |
| [benchmark_brief.md](benchmark_brief.md) | Security comparison across approach types |
| [WORKAROUNDS.md](WORKAROUNDS.md) | Tactical patterns implementable today without the full stack |
| [linkedin_posts_perception_world.md](linkedin_posts_perception_world.md) | Three LinkedIn posts: zombies & control illusion, flexibility myth, perception world |

---

## Reference & Context

| Document | Summary |
|---|---|
| [REFERENCES.md](REFERENCES.md) | Compiled case studies, academic papers, and industry coverage |
| [TIMELINE.md](TIMELINE.md) | Chronology of relevant industry developments |
| [../ROADMAP.md](../ROADMAP.md) | Development stages: PoC → Executable Proof → Beta Product |
| [../CHANGELOG.md](../CHANGELOG.md) | Version history (v0.1–v0.4) |

---

## Navigation by Role

### Security Researchers
[THREAT_MODEL.md](../THREAT_MODEL.md) → [VULNERABILITY_CASE_STUDIES.md](VULNERABILITY_CASE_STUDIES.md) → [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) → [EVALUATION_FRAMEWORK.md](EVALUATION_FRAMEWORK.md)

### AI Architects & System Designers
[WHITEPAPER.md](WHITEPAPER.md) → [../CONCEPT.md](../CONCEPT.md) → [../12-FACTOR-AGENT.md](../12-FACTOR-AGENT.md) → [ARCHITECTURE.md](ARCHITECTURE.md) → [ADR/](ADR/)

### Writers & Speakers
[pub/PUBLICATIONS_PLAN.md](pub/PUBLICATIONS_PLAN.md) → [pub/the-missing-layer/](pub/the-missing-layer/) → [../presentation-core/](../presentation-core/)

### Enterprise Decision Makers
[WHITEPAPER.md](WHITEPAPER.md) → [VS_EXISTING_SOLUTIONS.md](VS_EXISTING_SOLUTIONS.md) → [EVALUATION_FRAMEWORK.md](EVALUATION_FRAMEWORK.md) → [../FAQ.md](../FAQ.md)

### Developers (PoC / Integration)
[HELLO_WORLD.md](HELLO_WORLD.md) → [execution_governance.md](execution_governance.md) → [integrations.md](integrations.md) → [WORKAROUNDS.md](WORKAROUNDS.md)

### Academic Researchers
[WHITEPAPER.md](WHITEPAPER.md) → [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) → [VULNERABILITY_CASE_STUDIES.md](VULNERABILITY_CASE_STUDIES.md) → [REFERENCES.md](REFERENCES.md)
