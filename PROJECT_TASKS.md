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

### [x] README v2 — #1 (CLOSED)

**Labels:** docs, architecture, high-priority

**Goal:** Create a one-page overview explaining the raw reality problem, the shift from permission security to ontological security, and the core `Reality -> Hypervisor -> Agent` model.

**Tasks:**

- Explain why agents are unsafe in unvirtualized reality.
- Add the canonical formula: "We do not make agents safe. We make the world they live in safe."
- Add a short "What works today" section: prompt injection containment, taint containment, provenance tracking, deterministic intent handling.
- Add quickstart and link to `WHITEPAPER.md`.

**Acceptance criteria:**

- A new reader understands in under 10 minutes that the hypervisor virtualizes perception and action rather than filtering behavior.
- README terminology matches the whitepaper and core docs.

---

### [x] CONCEPT.md v2 — #2 (CLOSED)

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

### [ ] WHITEPAPER freeze v2 — #3 (OPEN)

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

### [ ] THREAT_MODEL.md — #4 (OPEN)

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

### [ ] ARCHITECTURE.md — #5 (OPEN)

**Labels:** docs, architecture

**Goal:** Provide a concise implementation-oriented architecture document.

**Tasks:**

- Document the runtime path: raw input -> semantic event -> trust assignment -> taint propagation -> capability lookup -> intent proposal -> policy decision -> audit trace.
- Document the compilation path: human intent + LLM semantic modeling -> World Manifest -> deterministic runtime artifacts.
- Add one reference diagram for runtime and compile flow.
- Map document sections to planned modules: compiler, runtime, gateway, demo.

**Acceptance criteria:**

- Someone can understand the reference architecture without reading the full whitepaper.
- The architecture doc maps directly to code modules.

---

### [x] FAQ.md — #6 (CLOSED)

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

### [x] GLOSSARY.md — #7 (CLOSED)

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

- Every core term used in docs and code has one canonical definition.
- No term changes meaning between documents.

---

### [x] ROADMAP.md — #8 (CLOSED)

**Labels:** docs, architecture

**Goal:** Show the Design -> Compile -> Deploy -> Learn -> Redesign cycle as the main delivery logic of the project.

**Tasks:**

- Link each phase to repo deliverables.
- Distinguish proof-of-concept, executable proof, and beta mini-product stages.

**Acceptance criteria:**

- After reading the roadmap, the sequence from architecture thesis to runnable proof is clear.

---

### [x] POSITIONING.md — #9 (CLOSED)

**Labels:** docs, product

**Goal:** Clearly separate architecture thesis, reference implementation, research claims, and practical mini-product.

**Tasks:**

- Fix the current goal as proof-of-concept and focused product surface, not universal agent platform.

**Acceptance criteria:**

- Project scope is unambiguous.
- Positioning matches whitepaper, article series, and repo docs.

---

## M2 Core Engine

### [x] World Manifest schema v1 — #10 (CLOSED)

**Labels:** compiler, architecture

**Goal:** Define the schema for all World Manifest sections.

**Tasks:**

- Describe schema for action ontology.
- Describe schema for trust channels and trust levels.
- Describe schema for capability matrix.
- Describe schema for taint propagation rules.
- Describe schema for escalation conditions and provenance settings.
- Prepare minimum 3 example manifests: `email-safe-assistant`, `mcp-gateway-demo`, `browser-agent-demo`.

**Acceptance criteria:**

- A valid manifest can be authored without reading source code.
- Example manifests cover prompt injection, tainted egress, and trusted workflow scenarios.

---

### [x] Compiler CLI — #11 (CLOSED)

**Labels:** compiler, high-priority

**Goal:** Implement `ahc build manifest.yaml` command.

**Tasks:**

- Generate policy lookup tables.
- Generate JSON validators for actions and intents.
- Generate taint matrices or equivalent state-machine artifacts.
- Generate capability graph and provenance-related validation structures.

**Acceptance criteria:**

- Same manifest always produces identical build output.
- Compiler output is human-readable and unit-testable.

---

### [x] Taint rule compiler — #12 (CLOSED)

**Labels:** compiler, runtime

**Goal:** Compile taint laws into state machine or lookup-table format.

**Tasks:**

- Start with base laws: untrusted source gets taint, derived data inherits taint, combining clean and untrusted yields untrusted, tainted data cannot cross external boundary.

**Acceptance criteria:**

- Base taint scenarios covered by unit tests.
- Taint propagation logic is reproducible and not dependent on LLM.

---

### [x] Semantic event model — #13 (CLOSED)

**Labels:** runtime, architecture

**Goal:** Introduce a unified runtime object for all inputs.

**Tasks:**

- Define runtime object: `source`, `trust_level`, `taint`, `provenance`, `sanitized_payload`.
- Forbid policy evaluation on raw input without event wrapping.
- Add serialization format for traces and replay.
- Migrate demo fixtures and tests to semantic events.

**Acceptance criteria:**

- All demos and tests use semantic events as the only input form.
- Raw input cannot reach policy evaluation layer.

---

### [ ] Intent proposal API — #14 (OPEN)

**Labels:** runtime, architecture

**Goal:** Implement a layer where the agent proposes only structured intent instead of direct tool invocation.

**Tasks:**

- Bind intent schema to compiled manifest artifacts.
- Run schema validation before policy decision.

**Acceptance criteria:**

- Runtime side effects are impossible without intent evaluation.
- Intent always passes schema validation before execution.

---

### [ ] Deterministic policy engine — #15 (OPEN)

**Labels:** runtime, high-priority

**Goal:** Implement evaluator with four verdicts: `allow`, `deny`, `require_approval`, `simulate`.

**Tasks:**

- Bind decision to capability matrix, trust context, taint state, and escalation conditions.
- Add human-readable trace with reason chain.
- Fix deterministic evaluation order.

**Acceptance criteria:**

- `Same manifest + same input = same decision`.
- Every decision has an auditable reason chain.

---

### [ ] Provenance graph — #16 (OPEN)

**Labels:** runtime

**Goal:** Implement tracking of object origin, operations, and trust transitions.

**Tasks:**

- Prepare machine-readable audit log for benchmark reports and future learning-gate scenarios.

**Acceptance criteria:**

- Any output in the demo can be explained through its source chain.
- Provenance log is saved separately from LLM reasoning and does not depend on prompt text.

---

### [ ] Determinism and ontology tests — #17 (OPEN)

**Labels:** runtime, benchmarks

**Goal:** Add tests for all architectural invariants.

**Tasks:**

- `untrusted input -> external action -> denied`
- `tainted data -> export attempt -> impossible`
- `trusted intent -> allowed action -> allowed`
- `same manifest + same input -> same decision`
- `action not in ontology -> cannot be proposed`

**Acceptance criteria:**

- All invariants are covered by automated unit tests.
- Tests run without mocking the agent.

---

## M3 Tool Boundary

### [ ] MCP proxy skeleton — #18 (OPEN)

**Labels:** mcp, gateway

**Goal:** Stand up a minimal gateway between the agent and 1–2 demo MCP tools.

**Tasks:**

- Route all tool calls through the proxy boundary only.
- Log each tool call, validation step, capability check, and final verdict.

**Acceptance criteria:**

- Direct tool invocation does not exist in the reference demo path.
- Every tool call has a trace.

---

### [ ] Tools as virtualized devices — #19 (OPEN)

**Labels:** mcp, architecture

**Goal:** Implement the rule that a tool exists for the agent only if defined in the World Manifest.

**Tasks:**

- Remove undefined tools from the available capability set.
- Reflect in trace that the tool "does not exist in the agent's world" rather than being "forbidden".

**Acceptance criteria:**

- Undefined tool does not participate in intent formation.
- The same tool can exist in one world and be absent from another.

---

### [ ] Tool descriptor schema — #20 (OPEN)

**Labels:** mcp, compiler

**Goal:** Describe typed input/output schema for each demo tool as a device descriptor.

**Tasks:**

- Connect compiled validators to the gateway execution path.
- Add schema versioning.

**Acceptance criteria:**

- Malformed payloads and unexpected fields are blocked before tool call execution.
- Tool schema versioning is reflected in manifest examples.

---

### [ ] Capability matrix enforcement — #21 (OPEN)

**Labels:** runtime, mcp

**Goal:** Implement different capability sets for different trust contexts.

**Tasks:**

- Verify that an untrusted channel cannot initiate an egress-capable path.

**Acceptance criteria:**

- The same tool can be visible or invisible depending on trust level.
- Trace shows which capability was absent.

---

### [ ] Taint-aware egress control — #22 (OPEN)

**Labels:** runtime, gateway

**Goal:** Implement external egress as a physics rule: tainted data cannot leave the system.

**Tasks:**

- Run exfiltration scenarios through email, tool, and API use cases.

**Acceptance criteria:**

- No tainted payload passes through demo egress tools.
- Reason for blocking is visible in trace and benchmark output.

---

### [ ] Provenance for tool outputs — #23 (OPEN)

**Labels:** runtime, mcp

**Goal:** Tag tool outputs and inter-agent channels as provenance and taint sources.

**Tasks:**

- Treat inter-agent communication as untrusted channel by default.

**Acceptance criteria:**

- Tool outputs and inter-agent inputs have a strict provenance trail.
- Trace shows where contamination enters, propagates, or stops.

---

## M4 Proof

### [ ] Interactive demo v1 — #24 (OPEN)

**Labels:** demo, high-priority

**Goal:** Build a web demo showing: raw input, canonicalized event, trust label, taint state, visible capabilities, proposed intent, final decision.

**Tasks:**

- Main scenario: injected email attempting to trigger an external side effect.
- Add trace view for explanation.

**Acceptance criteria:**

- User can see exactly where the attack loses effect.
- Demo explains the architecture without reading the whitepaper.

---

### [ ] Demo scenario 2 — poisoned tool output — #25 (OPEN)

**Labels:** demo

**Goal:** Add a scenario where a malicious tool output arrives as an untrusted channel and cannot trigger a dangerous downstream action.

**Tasks:**

- Show the difference between the direct-tool model and the hypervisor model.

**Acceptance criteria:**

- Scenario is reproducible across runs.
- Outcome and trace clearly demonstrate the value of tool mediation.

---

### [ ] Benchmark scenario taxonomy — #26 (OPEN)

**Labels:** benchmarks

**Goal:** Classify scenario set into `attack`, `safe`, `ambiguous`.

**Tasks:**

- Include prompt injection, memory poisoning surrogate cases, data exfiltration, and benign workflows.

**Acceptance criteria:**

- Each class has a minimally representative scenario set.
- Scenarios are stored as reproducible fixtures, not ad hoc tests.

*(Note: #27 is a duplicate of #26 — to be closed as duplicate.)*

---

### [ ] Baseline runner — #28 (OPEN)

**Labels:** benchmarks

**Goal:** Enable side-by-side comparison of "without hypervisor" and "with hypervisor" on the same scenarios.

**Tasks:**

- Use a maximally simple direct-agent path without a virtualization boundary as the baseline.

**Acceptance criteria:**

- The same case can be run in both modes.
- The difference is visible in outcome and trace.

---

### [ ] Metrics and report v1 — #29 (OPEN)

**Labels:** benchmarks

**Goal:** Compute and publish `benchmarks/reports/report-v1.md`.

**Tasks:**

- Metrics: `attack containment rate`, `taint containment rate`, `false deny`, `false escalation`, `task completion`, `latency overhead`, `deterministic coverage`.

**Acceptance criteria:**

- Report shows both security wins and utility cost.
- Metrics can be recomputed on new versions of manifest/compiler/runtime.

---

### [ ] Trace replay and walkthrough — #30 (OPEN)

**Labels:** demo, benchmarks

**Goal:** Add replay of any trace on the same manifest.

**Tasks:**

- Prepare a walkthrough of one case through the full `Design -> Compile -> Deploy -> Learn -> Redesign` cycle.

**Acceptance criteria:**

- Any trace can be reproduced by re-running it.
- Walkthrough shows how deterministic coverage grows after iterations.

---

## M5 Beta Product

### [ ] Docker local stack — #31 (OPEN)

**Labels:** product, gateway

**Goal:** Package gateway, demo tools, UI, and example manifests into a local run via Docker Compose.

**Tasks:**

- Focus the build on practical mini-product, not a universal platform.

**Acceptance criteria:**

- `docker compose up` starts a working demo locally.
- A fresh user completes the quickstart without manual assembly of components.

---

### [ ] Web UI for manifests, traces and decisions — #32 (OPEN)

**Labels:** product, demo

**Goal:** Build tabs: `manifests`, `decisions`, `traces`, `provenance`, `benchmark runs`.

**Tasks:**

- Show policy reasoning without needing to read internal logs.

**Acceptance criteria:**

- User can see why an action was allowed, denied, escalated, or simulated.
- Any trace can be opened and replayed from the UI.

---

### [ ] Quickstart and walkthrough — #33 (OPEN)

**Labels:** product, docs

**Goal:** Describe the path: start the stack, open demo, run an attack, view trace, change a manifest rule, rebuild, re-run.

**Tasks:**

- Keep the first end-to-end experience within 5–10 minutes.

**Acceptance criteria:**

- First useful result achieved in 5–10 minutes.
- User sees how a manifest change alters runtime physics and the final verdict.

---

### [ ] Content-to-proof packaging — #34 (OPEN)

**Labels:** product, docs

**Goal:** Link repo, whitepaper, article series, demo, and benchmark report into a single proof package.

**Tasks:**

- Ensure each article references a specific executable proof artifact.

**Acceptance criteria:**

- Repo reads as a coherent architecture-and-proof system, not a set of disconnected files.
- Narrative and executable proof are directly linked.
