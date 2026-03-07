# PROJECT_TASKS.md

Agent Hypervisor GitHub Project plan.

Milestones:
- M1 Foundation
- M2 Core Engine
- M3 Tool Boundary
- M4 Proof
- M5 Beta Product

Recommended labels:
- docs
- architecture
- compiler
- runtime
- mcp
- gateway
- demo
- benchmarks
- product
- high-priority
- good-first-proof

Issue template:
- Context
- Goal
- Tasks
- Acceptance criteria
- Out of scope

---

## M1 Foundation

### [ ] README v2
**Labels:** docs, architecture, high-priority  
**Goal:** Create a one-page overview explaining the raw reality problem, the shift from permission security to ontological security, and the core `Reality -> Hypervisor -> Agent` model.

**Tasks:**
- Explain why agents are unsafe in unvirtualized reality.
- Add the canonical formula: “We do not make agents safe. We make the world they live in safe.”
- Add a short “What works today” section: prompt injection containment, taint containment, provenance tracking, deterministic intent handling.
- Add quickstart and link to `WHITEPAPER.md`.

**Acceptance criteria:**
- A new reader understands in under 10 minutes that the hypervisor virtualizes perception and action rather than filtering behavior.
- README terminology matches the whitepaper and core docs.

---

### [ ] CONCEPT.md v2
**Labels:** docs, architecture, high-priority  
**Goal:** Write a short serious explainer for people who should understand the idea without reading the full whitepaper.

**Tasks:**
- Summarize the problem, hypervisor analogy, semantic isolation, and ontological security.
- Include the honest weakness: semantic gap.
- State the bounded measurable security claim instead of perfect security.
- Separate architecture thesis, current PoC status, and open questions.

**Acceptance criteria:**
- The doc can be shared standalone as the shortest credible explanation of the project.
- It clearly distinguishes what is already demonstrated from what is still a research claim.

---

### [ ] WHITEPAPER freeze v2
**Labels:** docs, architecture, high-priority  
**Goal:** Freeze one canonical whitepaper that acts as the source of truth for code, demo, and narrative.

**Tasks:**
- Unify terminology across core architecture, semantic gap, AI Aikido, World Manifest Compiler, design-time HITL, and MCP virtualization.
- Make the narrative flow explicit: claim -> objection -> resolution -> formalization -> bounded claim.
- Remove terminology drift and duplicated definitions.
- Ensure MVP section maps to implementation tasks.

**Acceptance criteria:**
- The same term does not change meaning between sections.
- The whitepaper can serve as the canonical reference for repo docs, implementation, and public articles.

---

### [ ] THREAT_MODEL.md
**Labels:** docs, architecture, high-priority  
**Goal:** Define the threat model and trust assumptions explicitly.

**Tasks:**
- Define trusted boundary and untrusted inputs.
- Document trust channels: user, email, web, file, MCP, agent-to-agent.
- Define capability assumptions and critical path.
- List in-scope threats: prompt injection, tainted egress, tool abuse, memory poisoning surrogate scenarios.
- List out-of-scope items and explicit constraints.

**Acceptance criteria:**
- A reader can point to the exact virtualization boundary and trust assumptions.
- Non-goals are as explicit as goals.

---

### [ ] ARCHITECTURE.md
**Labels:** docs, architecture  
**Goal:** Provide a concise implementation-oriented architecture document.

**Tasks:**
- Document the runtime path: raw input -> semantic event -> trust assignment -> taint propagation -> capability lookup -> intent proposal -> policy decision -> audit trace.
- Add one reference diagram for the full path.
- Map document sections to planned modules: compiler, runtime, gateway, demo.

**Acceptance criteria:**
- Someone can understand the reference architecture without reading the full whitepaper.
- The architecture doc maps directly to code modules.

---

### [ ] FAQ.md
**Labels:** docs  
**Goal:** Answer the main objections before people ask them.

**Tasks:**
- Explain how this differs from a guardrail, policy engine, sandbox, or plain MCP proxy.
- Explain what the semantic gap means in practice.
- Explain why human-in-the-loop belongs primarily at design-time, not runtime.
- Explain what remains unsolved.

**Acceptance criteria:**
- FAQ addresses the main conceptual objections clearly.
- Each answer points to a specific architectural principle, not marketing language.

---

### [ ] GLOSSARY.md
**Labels:** docs  
**Goal:** Freeze canonical definitions.

**Tasks:**
- Define semantic event.
- Define intent proposal.
- Define World Manifest.
- Define capability matrix.
- Define taint propagation.
- Define provenance.
- Define escalation condition.
- Define virtualized device.

**Acceptance criteria:**
- Every core term used in docs and code has one canonical
