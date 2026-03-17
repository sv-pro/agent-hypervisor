# Agent Hypervisor: Deterministic Virtualization of Reality for AI Agents

## Architecture, AI Aikido, World Manifest Compiler, and Design-Time Human-in-the-Loop

---

## Origin Insight: The Moment Stochastic Became Deterministic

A demo of GitHub Copilot using Playwright MCP to test a web application. The AI agent reads a prompt, navigates the browser, clicks elements, verifies states — a fully stochastic process. Each run is potentially different. The LLM interprets, decides, acts. This is an agent living in raw reality.

Then a seemingly trivial question: *Can another prompt capture all of these test operations as code — a standard Playwright script that runs without the LLM?*

The answer is yes. And that "yes" is the entire thesis of this project in a single moment.

The same tool — Playwright — operates in two fundamentally different modes:

| Mode                  | Driver                        | Behavior                       | Reproducibility |
| --------------------- | ----------------------------- | ------------------------------ | --------------- |
| Stochastic runtime    | LLM interprets prompt via MCP | Each run potentially different | None guaranteed |
| Deterministic runtime | Generated Playwright script   | Identical every time           | Full            |

The boundary between stochastic and deterministic does not run between systems. It runs between **phases**. The LLM participates in the generation phase. The generated artifact executes without it.

This is not a curiosity. It is the foundational pattern:

> **Every time an LLM generates code that is then compiled and executed, a stochastic process has produced a deterministic artifact.**

Copilot generating a function. Cursor generating a module. ChatGPT generating a SQL query. Claude generating a Terraform config. The entire industry practices this pattern daily — without naming it, and without applying it to the domain where it is most critically needed: **agent security**.

Agent Hypervisor takes this pattern and applies it deliberately:

- Where Copilot generates **application code** → Agent Hypervisor generates **security parsers**
- Where Cursor generates **modules** → Agent Hypervisor generates **World Manifests**
- Where ChatGPT generates **SQL** → Agent Hypervisor generates **taint propagation rules**

The principle we call **AI Aikido**: use the LLM's own capability to build the deterministic cage in which agents safely operate. The stochastic system constructs the deterministic system. Intelligence designs the physics; it does not govern the physics at runtime.

This document formalizes that insight into an architecture.

---

## Part I — Core Architecture

### 1. The Problem

Modern AI agents are unsafe not because they are intelligent, but because they inhabit **raw reality**: unmediated access to untrusted text, unconstrained memory, unfiltered tools, and irreversible consequences.

Traditional defenses — guardrails, prompt filters, output classifiers, LLM-based safety layers — operate **after** the agent has already perceived dangerous input. They ask: *"Can agent X perform action Y?"* and answer with a probabilistic runtime check.

The evidence is unambiguous:

- Adaptive attacks achieve **90–100% bypass rates** against published defenses (Yi et al., 2025).
- OpenAI acknowledges prompt injection is **"unlikely to ever be fully solved"** at the behavioral layer.
- Anthropic's own evaluations conclude that even a 1% Attack Success Rate constitutes **"meaningful risk"** at scale.
- ZombieAgent (Radware, January 2026) demonstrates **persistent memory poisoning** — malicious instructions that survive across sessions with 90% data leakage rates.
- Dario Amodei (Anthropic CEO, February 13, 2026) expects continuous learning in 1–2 years — meaning memory poisoning becomes **permanent corruption**.

These are not bugs. They are **architecturally predictable consequences** of agents operating in unvirtualized reality.

### 2. The Thesis

Agent Hypervisor proposes a fundamentally different question:

> **"Does action Y exist in agent X's universe?"**

This is **ontological security** — not permission-based, but construction-based. Dangerous actions are not prohibited by rules; they are **absent from the world the agent inhabits**. This answer emerges from Layers 0–2 working together: Layer 0 (Execution Physics) removes physical impossibilities at the infrastructure level; Layer 1 (Base Ontology) defines what actions exist in the design-time vocabulary; Layer 2 (Dynamic Ontology Projection) projects the actor-visible subset of those actions at runtime. Governance (Layer 3) handles what ontology alone cannot cover — contextual risk at runtime, where the action exists but circumstances make it unsafe.

The classical hypervisor analogy holds precisely:

| Classical Hypervisor             | Agent Hypervisor                                          |
| -------------------------------- | --------------------------------------------------------- |
| Virtualizes CPU, RAM, I/O        | Virtualizes meaning, actions, consequences                |
| VM cannot see physical memory    | Agent cannot see raw reality                              |
| MMU/IOMMU make access impossible | Policies make dangerous actions ontologically nonexistent |
| Guest is free inside its VM      | Agent is free inside its virtualized world                |

The core principle: **not "prohibit," but "do not provide."**

### 3. What Agent Hypervisor Is Not

Boundaries matter. Agent Hypervisor is not:

- An agent orchestrator
- A guardrail, filter, or classifier
- An LLM-based security agent
- A workflow engine
- A policy-only wrapper over tools
- Just a runtime gateway

It is a **four-layer system**: Execution Physics (Layer 0), Base Ontology (Layer 1), Dynamic Ontology Projection (Layer 2), and Execution Governance (Layer 3). The execution governance gateway is its runtime component — one layer of four, not the whole system.

It is a **compiler for secure semantic worlds**.

Comparable to: Infrastructure-as-Code compilers, type systems, capability-based OS design, and classical hypervisors — but applied to meaning.

### 4. Runtime Architecture

```text
[ Raw Reality ]
       ↓
[ Agent Hypervisor — Virtualization Boundary ]
       ↓
[ Agent (LLM / Planner) — Virtualized World ]
```

The system intercepts all perception, intercepts all actions, and defines the physics of the agent's world across four layers.

#### 4.1 Four-Layer Architecture

```text
  ┌──────────────────────────────────────────────────────────────┐
  │  Layer 0: Execution Physics                                  │
  │  Sandbox, container, network/filesystem isolation            │
  │  Makes certain actions physically impossible at the          │
  │  infrastructure level — not by rule, but by absence          │
  └──────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Layer 1: Base Ontology (design-time)                        │
  │  The vocabulary of actions the agent may ever propose.       │
  │  Capability construction: tool specialization, parameter     │
  │  validation, schema enforcement. Actions not defined here    │
  │  do not exist — the agent cannot formulate intent for them.  │
  └──────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Layer 2: Dynamic Ontology Projection (runtime context)      │
  │  Projects the base ontology to a context-dependent subset    │
  │  visible to the actor. Semantic Event construction, trust    │
  │  classification, taint assignment. Role, task, environment,  │
  │  and approvals determine what the actor can propose now.     │
  └──────────────────────────┬───────────────────────────────────┘
                             │  proposed action
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Layer 3: Execution Governance Gateway                       │
  │  Evaluates proposed actions deterministically — no LLM.      │
  │  Provenance chains, policy rules, taint checks,              │
  │  reversibility classification, budget enforcement.           │
  │  Decisions: allow | deny | require_approval | simulate       │
  └──────────────────────────────────────────────────────────────┘
```

| Agent Hypervisor                     | Operating System                    |
| ------------------------------------ | ----------------------------------- |
| Layer 0: Execution Physics           | Hardware isolation (MMU, rings)     |
| Layer 1: Base Ontology               | Syscall interface                   |
| Layer 2: Dynamic Ontology Projection | File descriptors, capabilities      |
| Layer 3: Execution Governance        | ACL, SELinux, sandbox policies      |
| Actor                                | Process                             |
| Action                               | System call                         |

#### 4.2 Core Mechanisms

**Semantic Events (Perception) — Layer 2**

Layer 2 (Dynamic Ontology Projection) constructs structured events from raw input before the actor perceives anything. The actor never receives raw input. It receives structured events:

- `source` — email, web, file, MCP, user
- `trust_level` — trusted / untrusted / tainted
- `capabilities` — what is permitted in this context
- `sanitized_payload` — stripped of hidden instructions

For the actor, "just text" does not exist.

**Intent Proposals (Action) — Layer 2**

The actor cannot act directly. Working within its Layer 2 projected tool set, it can only propose an intent:

- `send_email(...)`, `write_file(diff=...)`, `run_tool(...)`, `query_resource(...)`

This is a proposal, not an execution. Only actions present in the actor's projected tool set can be proposed — the rest are unrepresentable.

**Governance Policy (Layer 3) and Base Ontology (Layer 1)**

Two distinct concerns, two distinct layers:

*Base Ontology (Layer 1)* defines what actions exist at all. Its rules are:
- Deterministic — same manifest, same vocabulary, always
- Design-time — compiled before deployment
- Testable — "action not in ontology → cannot be proposed"

*Governance Policy (Layer 3)* evaluates whether a proposed action may execute at runtime:
- Deterministic — same input, same decision, always
- Reproducible — fully auditable
- Testable — unit tests for security properties
- LLM-free on the critical path

Decisions: `allow` | `deny` | `require_approval` | `simulate`

**Taint Propagation and Provenance**

Data carries its origin and contamination status as physical properties:

- Taint spreads through operations automatically
- Tainted data **cannot** cross external boundaries — not by rule, but by construction
- Every object knows its provenance chain

Provenance tracking is a Layer 3 (governance) mechanism. Some taint containment — such as network-level exfiltration blocking — operates at Layer 0 (Execution Physics). These are not restrictions. They are **physics laws** of the agent's world, enforced at different layers of the stack.

#### 4.3 Tool Integration (MCP Model)

Raw tools are transformed by Layer 1 (Base Ontology) into specialized capabilities with typed schemas and constrained parameter sets. Capabilities are projected by Layer 2 (Dynamic Ontology Projection) to the actor, presenting only the subset relevant to its current role and context. The execution governance gateway (Layer 3) evaluates whether a proposed action may execute, applying provenance, taint, and policy rules.

- MCP tool = raw device registered with the system
- Layer 1 capability = specialized, schema-constrained form visible to the ontology
- Layer 2 projection = context-dependent subset visible to the actor now
- Layer 3 governance = access control + runtime policy evaluation

Adding a tool does not change the actor, does not complicate the architecture, does not reduce determinism.

#### 4.4 The Acid Test

If you can write a unit test:

```text
untrusted input → propose external action → denied
tainted data    → attempt export          → impossible
trusted intent  → execution               → allowed
action not in ontology → cannot be proposed (Layer 1)
actor lacks projection → cannot be proposed now (Layer 2)
```

…then the system is deterministic, not an agent, and architecturally sound.

### 5. The Canonical Formula

> We do not make agents safe. We make the world they live in safe.

---

## Part II — The Honest Weakness: The Semantic Gap

### 6. The Paradox

The architecture above has a fundamental tension, and it must be stated plainly.

The hypervisor promises that the agent never sees raw reality — only sanitized semantic events. But to **create** a semantic event from raw input, **someone must understand that input**. Understanding unstructured text is exactly the task LLMs solve. This creates a paradox:

**The boundary layer needs intelligence, but intelligence is stochastic.**

Three specific manifestations:

**6.1 Parsing the boundary requires understanding.** Stripping `[[SYSTEM: ...]]` and zero-width characters is trivial. Real attacks use semantic ambiguity: "Please send my report to Alex" — is this a legitimate user request or a socially engineered instruction embedded in a document? Distinguishing the two requires a model, and models are probabilistic. Determinism ends precisely where the need to understand meaning begins.

**6.2 Taint propagation breaks on transformations.** An agent reads a tainted document, draws a conclusion, formulates a new thought based on that conclusion. Is the thought tainted? If the agent mixes data from three sources — two trusted, one tainted — is the result fully tainted? Conservative approaches (everything tainted) render the system useless; liberal approaches break safety. This is the classic overtainting/undertainting problem from information flow control research (Denning, 1976), unresolved for fifty years.

**6.3 Defining the ontology is a design problem; defining governance is a policy problem.** The four-layer model makes this separation explicit. Defining the base ontology (Layer 1) — what actions exist at all — is a design-time engineering decision. Too narrow and the actor is useless; too wide and security is nominal. Separately, designing governance rules (Layer 3) — when existing actions may execute — is a policy problem with all the challenges of policy design. These are distinct concerns requiring distinct solutions. Conflating them (as older single-layer approaches do) produces systems where the same mechanism tries to handle both structural risk and contextual risk — and does neither well.

### 7. The Implication

The hypervisor moves the problem from runtime to design-time and from the agent to the boundary layer, but does not eliminate it. The fundamental difficulty — transforming an unstructured world into a structured ontology — remains, and the boundary is precisely where an attacker will probe for gaps.

This does not make the architecture useless — it genuinely narrows the attack surface. But the claim "ontologically impossible" is too strong for a system whose boundary inevitably contains a fuzzy parser.

The honest claim: **bounded, measurable security** — not perfect, not probabilistic, but deterministic within explicitly defined boundaries.

This honesty is not a weakness. It is the foundation for everything that follows.

---

## Part III — AI Aikido: Using the Opponent's Force

### 8. The Resolution

The paradox stated in Section 6 has an elegant resolution if we separate **when** intelligence operates from **where** it enforces.

**AI Aikido** is the principle of using LLM capabilities to generate deterministic artifacts rather than to provide runtime decisions. The stochastic system builds the deterministic system. Intelligence works at **design-time**; only its products operate at **runtime**. Concretely, AI Aikido primarily generates Layer 1 artifacts (ontology definitions, capability specifications, action schemas) and Layer 3 artifacts (governance rules, taint policies, escalation conditions). Layer 0 is infrastructure configuration; Layer 2 projection rules emerge from the combination of Layer 1 definitions and role/context assignments.

This breaks the paradox along the time axis:

> The boundary needs intelligence to understand the world.
> Intelligence is stochastic.
> Therefore, use intelligence **before deployment** to generate deterministic parsers, rules, schemas, and World Manifests.
> At runtime, only the deterministic artifacts execute.

**LLM creates the physics. LLM does not govern the physics in real time.**

This is not a novel pattern. It is the pattern the entire software industry already practices — every Copilot suggestion that becomes committed code, every LLM-generated SQL query that executes deterministically, every Terraform config that provisions infrastructure. AI Aikido names this pattern and applies it deliberately to agent security.

### 9. Concrete Applications

#### 9.1 Parser and Canonicalizer Generation

An LLM analyzes a corpus of real inputs — emails, documents, MCP schemas, API payloads — and generates specific deterministic artifacts: regular expressions for known attack patterns, PEG grammars for structured input validation, JSON Schema validators for tool interfaces, canonicalization rules for Unicode normalization and encoding standardization.

Each generated artifact is deterministic, testable, and verifiable. The LLM does not parse at runtime — **code generated by the LLM** parses at runtime.

#### 9.2 Automated World Manifest Creation

Given a description of a business process, an LLM generates the set of permitted actions and their schemas, trust relationships between input channels, capability presets per trust level, taint propagation rules, and escalation conditions. This process explicitly constructs the **base ontology (Layer 1)**: the design-time vocabulary of actions, their typed schemas, and the capability specifications that bound what actors can ever propose.

A human reviews, modifies, and commits. The manifest becomes the constitution of the agent's world — written with AI assistance, executed deterministically.

#### 9.3 Adversarial Red-Teaming of Parsers

The same LLM (or a different one) attacks the generated parsers — generates adversarial inputs designed to bypass canonicalization, probes for edge cases in grammar definitions, crafts semantic ambiguity attacks, tests taint propagation boundaries.

The cycle: **generate → attack → patch → re-attack** — all in design-time. The parsers that survive are deployed; the ones that fail are iterated.

#### 9.4 Context-Aware Taint Rules

An LLM analyzes the data flow of a specific application and proposes taint propagation rules: "If source is email and transformation is `summarize`, taint is preserved." "If transformation is `count_words`, taint is cleared." "If three sources are mixed and any is tainted, result is tainted unless transformation is `aggregate_statistics`."

A human approves each rule. The rule becomes a deterministic physics law — specifically, a **Layer 3 governance rule**: runtime policy encoding the LLM's semantic understanding of data transformations as a deterministic enforcement artifact. The LLM's understanding of semantic transformations informs the rule; the rule itself contains no stochasticity.

### 10. What AI Aikido Does Not Solve

**Coverage completeness.** LLM-generated parsers cover known attack patterns and patterns the LLM can anticipate. An attacker may find a pattern absent from design-time analysis. However, this is now a manageable engineering problem — parsers can be iterated, adversarial testing automated, coverage expanded incrementally.

**Semantic ambiguity.** "Send the report to Alex" remains ambiguous regardless of design-time effort. AI Aikido can generate the policy rule, but the **correctness** of that rule is a human judgment.

**Adaptation latency.** New attack type → new parser needed → LLM generates → testing → deployment. Faster than manual authoring, but not instantaneous. The gap is finite and measurable, unlike the infinite gap of hoping a runtime probabilistic filter catches an unknown pattern.

---

## Part IV — The World Manifest Compiler

### 11. Agent Hypervisor as a Compiler

Agent Hypervisor is not primarily a runtime policy engine. It is a **design-time compiler** that transforms human + LLM semantic intent into deterministic runtime physics.

The compilation pipeline:

```text
Human intent + LLM semantic modeling
              ↓
     World Manifest (reviewed & committed)
              ↓
     Compilation phase
              ↓
     Deterministic runtime artifacts
              ↓
     Runtime enforcement (LLM-free)
```

### 12. The World Manifest

The World Manifest is a formal, structured document (YAML / DSL) that defines everything that exists in the agent's universe:

**Base Ontology (Layer 1)** — the complete set of actions the actor can ever propose, with typed schemas. Actions not in the ontology do not exist. The actor cannot formulate intent for them because they are absent from its world definition. This is the design-time vocabulary compiled before deployment.

**Trust Model** — trust channel definitions (user, email, web, file, MCP) and their design-time trust levels belong to Layer 1. Runtime trust assignment — applying those channel definitions to incoming data — is a Layer 3 governance mechanism. Trust is a property of the channel, not the content.

**Capability Matrix (Layer 2)** — projection rules specifying which capabilities are available at which trust levels and context. A matrix, not a list of rules. Capabilities define what is physically possible for the actor right now, projecting the base ontology to its current context.

**Taint Propagation Rules (Layer 3)** — deterministic rules for how contamination spreads through data transformations, evaluated by the execution governance gateway. Each rule specifies: source trust level × transformation type → output taint status. These are the thermodynamic laws of the agent's world.

**Escalation Conditions (Layer 3)** — explicit boundaries where the governance gateway transitions from deterministic decision to human review. Defined narrowly: the goal is to minimize runtime escalation through comprehensive design-time coverage.

**Provenance Schema (Layer 3)** — how origin metadata propagates through the system, tracked and enforced by the governance gateway. Every object carries its lineage. Critical for continuous learning safety: only data with verified provenance enters the learning loop.

### 13. The Compilation Phase

The compiler transforms the World Manifest into executable runtime artifacts:

| Manifest Element        | Layer | Compiled Artifact                      |
| ----------------------- | ----- | -------------------------------------- |
| Base ontology           | L1    | Validated JSON Schemas + intent parser |
| Trust channel defs      | L1    | Trust channel registry                 |
| Capability matrix       | L2    | Static capability lookup / projection engine |
| Runtime trust assignment| L3    | Deterministic trust assignment tables  |
| Taint propagation rules | L3    | Taint propagation matrices             |
| Escalation conditions   | L3    | Threshold evaluators                   |
| Provenance schema       | L3    | Provenance chain validators            |

Layer 0 (Execution Physics) is infrastructure configuration — not compiler output.

**No LLM survives this phase.** The output is pure deterministic code — lookup tables, state machines, validators. Every compiled artifact is unit-testable. Every decision is reproducible.

### 14. Runtime Execution

At runtime, the compiled artifacts execute without stochasticity:

1. Raw input arrives at the virtualization boundary *(Layer 0/1 boundary)*
2. Compiled canonicalizer strips known attack patterns *(Layer 0/1 boundary)*
3. Trust assignment applies channel definitions to incoming data *(Layer 2)*
4. Taint propagation matrix computes contamination status *(Layer 3)*
5. Capability lookup projects available actions for this actor context *(Layer 2)*
6. Actor proposes an intent (structured JSON only, from within its Layer 2 projected tool set)
7. Governance policy evaluates: `allow` | `deny` | `require_approval` | `simulate` *(Layer 3)*
8. Decision is logged with full provenance for audit *(Layer 3)*

All decisions are reproducible. Same manifest + same input = same decision, always.

---

## Part V — Design-Time Human-in-the-Loop

### 15. The Fundamental Theorem

The discussions above converge on a single architectural principle:

> **Human judgment is necessary, but must be amortized through design-time rather than expended at runtime.**

This is not a compromise. It is the only architecture that is simultaneously **honest** (acknowledges the necessity of human judgment) and **scalable** (does not insert a human into every request).

### 16. Three Modes of Human Involvement

#### 16.1 Design-Time Human (Scales)

The human reviews and approves:

- Base Ontology definitions (Layer 1) — action schemas, capability specifications, trust channel definitions
- Governance rules (Layer 3) — taint propagation rules, escalation thresholds, provenance requirements
- Capability projection matrices (Layer 2) — which capabilities are available at which trust levels
- LLM-generated parsers and canonicalizers (Layer 1/2 boundary)

**One design-time decision amortizes across thousands of runtime decisions.** This is analogous to writing a constitution: expensive to draft, but its cost is amortized across every citizen and every moment of governance.

#### 16.2 Runtime Human — Exception, Not Rule

The `require_approval` decision is a **Layer 3 only** escape hatch — the `ask` verdict from the execution governance gateway for cases that design-time did not fully cover. It is not the primary path; it is the pressure relief valve.

**Critical signal:** If `require_approval` fires frequently, it means the World Manifest is underdefined. This is not a failure — it is a feedback signal that triggers a design-time iteration.

#### 16.3 Iteration-Time Human (Feedback Loop)

Runtime logs reveal patterns:

- "47 requests this week escalated to `require_approval` on rule X"
- "12 taint propagation ambiguities on transformation Y"
- "Zero bypasses on parser set Z"

The human analyzes patterns. The LLM generates updated parsers and rules. Tests run. Deployment follows. The number of runtime escalations drops. The system learns — but through **deterministic artifacts**, not through stochastic adaptation.

### 17. The Economics

Traditional human-in-the-loop spends human attention **linearly** — each decision costs the same.

Agent Hypervisor with AI Aikido spends human attention **logarithmically** — each design-time iteration covers exponentially more runtime cases.

```text
Traditional HITL:    Cost = O(n)      per runtime decision
Design-Time HITL:    Cost = O(log n)  per design iteration covering n decisions
```

As the system matures, the share of `require_approval` decisions trends toward zero, deterministic coverage trends toward completeness, and human effort concentrates on novel edge cases rather than routine decisions.

This is precisely the model that made classical hypervisors viable: VMware engineers did not sit beside every VM. They designed isolation rules once, and VMs scaled without human intervention.

### 18. The Four-Phase Cycle

```text
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌─────────┐   ┌──────────────┐  │
│  │  DESIGN  │──▶│ COMPILE  │──▶│ DEPLOY  │──▶│    LEARN     │  │
│  │          │   │          │   │         │   │              │  │
│  │ Human +  │   │ Manifest │   │ Runtime:│   │ Logs,        │  │
│  │ LLM co-  │   │ → deter- │   │ purely  │   │ escalation   │  │
│  │ create   │   │ ministic │   │ deter-  │   │ patterns,    │  │
│  │ manifest │   │ artifacts│   │ ministic│   │ coverage     │  │
│  └──────────┘   └──────────┘   └─────────┘   └──────┬───────┘  │
│       ▲                                              │          │
│       │              ┌──────────┐                    │          │
│       └──────────────│ REDESIGN │◀───────────────────┘          │
│                      │          │                               │
│                      │ Human    │                               │
│                      │ reviews, │                               │
│                      │ LLM re-  │                               │
│                      │ generates│                               │
│                      └──────────┘                               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Design:** Human + LLM co-create the World Manifest. LLM generates action schemas (Layer 1), trust policies and capability projections (Layer 2), taint rules and governance conditions (Layer 3), canonicalization logic (Layer 1/2 boundary). Human reviews and commits. The cycle produces artifacts for Layers 1, 2, and 3; Layer 0 is infrastructure configuration, not cycle output.

**Compile:** The World Manifest Compiler transforms the manifest into deterministic artifacts — policy tables (L3), JSON schemas (L1), taint matrices (L3), capability projection engine (L2). No LLM survives this phase. All artifacts are unit-testable.

**Deploy:** Runtime executes purely deterministic compiled artifacts across all four layers. No LLM on the critical path. No human in the loop. Decisions are reproducible and auditable.

**Learn:** Runtime logs accumulate. Escalation patterns (Layer 3) emerge. Coverage gaps in the base ontology (Layer 1) become visible. Metrics quantify deterministic coverage vs. exception rate.

**Redesign:** Human reviews patterns. LLM generates updated manifest elements — new parsers (Layer 1), refined governance rules (Layer 3), expanded action ontologies (Layer 1). Adversarial testing validates. The manifest is recompiled. The cycle repeats with higher coverage.

---

## Part VI — Positioning Within the L∞ Stack

### 19. Layer Mapping

The Agent Hypervisor maps onto the L∞ stack architecture for reliable agent systems:

| L∞ Layer                       | Agent Hypervisor Role                                                 |
| ------------------------------ | --------------------------------------------------------------------- |
| LLM Core (System 1)            | Design-time: generates manifest elements via AI Aikido                |
| Strict AI (Structured I/O)     | Compilation target: enforces schemas, validates intent proposals      |
| Semantics & Ontology           | World Manifests — formal representation of agent's permitted universe |
| Semantic Context Orchestration | Controls what knowledge enters agent's context window                 |
| Reasoning Layer (System 2)     | Agent's planning and reasoning — free within virtualized world        |
| L∞ Layer (Semantic Security)   | **Agent Hypervisor itself** — the virtualization boundary             |

The formula:

> **WAF = L7 Security** (network stack protection)
> **Agent Hypervisor = L∞ Security** (semantic stack protection)

AI Aikido is the bridge: LLM Core generates artifacts that the L∞ Layer compiles and enforces deterministically.

---

## Part VII — Minimal Viable Proof

### 20. MVP Specification

The architecture must be proven executable, not metaphorical. A runnable proof-of-concept is available in [`examples/`](../examples/). The minimal viable proof consists of:

**20.1 World Manifest Format**

A YAML-based manifest defining:

```yaml
# Example: minimal World Manifest
version: "1.0"
name: "email-assistant-world"

# Layer 1: Base Ontology — the design-time vocabulary of all possible actions
actions:
  read_email:
    type: read
    schema: { source: string, subject: string, body: string }
  send_email:
    type: external_side_effect
    schema: { to: string, subject: string, body: string }
    requires: [external_side_effects]
  summarize:
    type: internal_write
    schema: { content: string, format: string }

# Layer 1 (design-time defs) + Layer 3 (runtime trust assignment)
trust_channels:
  user:    { level: trusted,   default_caps: [read, internal_write, external_side_effects] }
  email:   { level: untrusted, default_caps: [read] }
  web:     { level: untrusted, default_caps: [read] }

# Layer 3: Governance Policy — taint propagation rules evaluated at runtime
taint_rules:
  - source: untrusted
    transform: summarize
    output_taint: preserved
  - source: untrusted
    transform: count_words
    output_taint: cleared
  - source: any_tainted
    action: external_side_effect
    decision: deny
    rule: TaintContainmentLaw

# Layer 3: Governance Policy — escalation conditions
escalation:
  - condition: "action.type == external_side_effect AND trust < trusted"
    decision: require_approval

# Layer 3: Governance Policy — provenance tracking
provenance:
  track: true
  learning_gate: "provenance.verified == true"
```

**20.2 Compiler**

A compiler that transforms the manifest into artifacts for Layers 1, 2, and 3. Layer 0 is infrastructure configuration, not compiler output.

- Deterministic policy lookup tables *(Layer 3)*
- JSON Schema validators for each action *(Layer 1)*
- Taint propagation state machine *(Layer 3)*
- Capability projection engine *(Layer 2)*
- Unit-testable rule set

**20.3 Runtime Engine**

A deterministic engine that:

- Accepts structured intent proposals (JSON)
- Evaluates against compiled artifacts
- Returns: `allow` | `deny` | `require_approval` | `simulate`
- Logs every decision with full provenance

**20.4 Test Suite**

Unit tests proving invariant enforcement (see [`examples/basic/01_simple_demo.py`](../examples/basic/01_simple_demo.py) for a runnable demonstration):

```text
TEST: untrusted input → external action → DENIED (TaintContainmentLaw)           [Layer 3]
TEST: tainted data → export attempt → IMPOSSIBLE (physics)                        [Layer 3]
TEST: trusted user intent → allowed action → ALLOWED                              [Layer 3]
TEST: same manifest + same input → same decision (determinism)                    [all layers]
TEST: action not in ontology → cannot be proposed (ontological security)          [Layer 1]
TEST: actor with role X → sees only tools A, B, C (projection)                   [Layer 2]
TEST: action in ontology but not in actor's projection → cannot be proposed now   [Layer 2]
```

**20.5 Success Criteria**

The MVP proves three things:

1. **Executable, not metaphorical** — the architecture runs, not just describes
2. **Deterministic** — identical inputs produce identical outputs across runs
3. **Testable** — security properties are verified by automated tests, not hoped for

---

## Part VIII — Honest Constraints

### 21. What This Is Not

This is not perfect security. It is **bounded, measurable security**.

**Manifest completeness is finite, not absolute.** The World Manifest covers what was anticipated at design-time. Novel attack patterns require redesign and recompilation.

**Semantic ambiguity is resolved by policy, not eliminated.** When the system encounters genuinely ambiguous input, it applies a deterministic rule — but the correctness of that rule depends on human judgment at design-time.

**Adaptation is not instantaneous.** New attack → redesign → recompile → redeploy. The cycle is faster with AI Aikido than with manual authoring, but a latency window exists.

**Human responsibility remains.** The system amortizes human judgment; it does not remove it. A poorly designed World Manifest produces a poorly secured world.

**The attack surface narrows but does not vanish.** It shifts from "can the agent be tricked at runtime?" to "is the manifest complete and are the parsers correct?" This is a strictly better position — parser correctness is testable, manifest completeness is measurable — but it is not invulnerability.

### 22. Why Honesty Matters

Every constraint above is deliberately stated because the alternative — claiming "ontologically impossible" without qualification — is the kind of overreach that discredits architectural proposals.

The honest framing:

> Agent Hypervisor turns security from an unbounded probabilistic problem into a bounded deterministic engineering problem. The bounds are explicit, measurable, and improvable through iteration. This is not the same as solving security. It is making security tractable.

---

## Part IX — Summary

### 23. What This Architecture Achieves

1. **Ontological security** — dangerous actions do not exist in the agent's world, rather than being prohibited by rules.

2. **Deterministic runtime** — no LLM, no probabilistic filter, no stochastic decision on the critical security path. Same input produces the same decision, always.

3. **Honest acknowledgment of the semantic gap** — the boundary between raw reality and structured ontology requires intelligence, and that intelligence is stochastic.

4. **Resolution through temporal separation (AI Aikido)** — stochastic intelligence operates at design-time to generate deterministic artifacts. Runtime executes only those artifacts.

5. **Compilation as the bridge** — the World Manifest Compiler transforms human + LLM intent into verified, testable, deterministic enforcement code.

6. **Scalable human judgment (Design-Time HITL)** — human expertise is amortized across thousands of runtime decisions through the Design → Compile → Deploy → Learn → Redesign cycle.

7. **Self-improving determinism** — each iteration cycle expands deterministic coverage, reducing the exception rate toward zero without introducing stochasticity into runtime.

8. **Bounded, measurable security** — not a claim of invulnerability, but a transformation of security from unbounded probabilistic problem to bounded deterministic engineering problem.

### 24. The Revised Canonical Formula

> We do not make agents safe.
> We make the world they live in safe.
> We use intelligence to design that world — but never to govern it at runtime.
> We compile intent into physics.

---

## Appendix A — Key Terms

*For all definitions and concepts concerning Agent Hypervisor, please refer to the core [Glossary](GLOSSARY.md).*

## Appendix B — Key References

- **ZombieAgent** — Radware research (January 2026): Persistent malicious instructions in agent memory
- **Adaptive Attacks Study** — Yi et al. (2025): 90–100% bypass rates on 12 published defenses
- **OpenAI Statement** (December 2025): Prompt injection "unlikely to ever be fully solved"
- **Anthropic ASR Evaluation** (February 2026): 1% attack rate = "still meaningful risk"
- **Dario Amodei Interview** (February 13, 2026): Continuous learning expected in 1–2 years
- **Capability-Based Security** — Dennis & Van Horn (1966): "Does capability exist?" vs "Is permission granted?"
- **Information Flow Control** — Denning (1976): Taint tracking and provenance foundations
- **Hypervisor Security Model** — Popek & Goldberg (1974): Virtual machine isolation principles

## Appendix C — Evolution of the Idea

The architecture presented here evolved through a specific intellectual trajectory:

1. **Core thesis** — Agent Hypervisor virtualizes reality, not behavior. Ontological security over permission security.
2. **Self-critique** — The semantic gap: the virtualization boundary itself needs intelligence, creating a paradox with the determinism requirement.
3. **Resolution (AI Aikido)** — Separate when intelligence operates from where it enforces. Stochastic design-time, deterministic runtime.
4. **Generalization** — All LLM code generation is the same pattern. The industry already practices AI Aikido daily; it just hasn't applied it to agent security.
5. **Origin insight** — Copilot + Playwright MCP demo: the moment a stochastic test run became a deterministic script through one additional prompt.
6. **Human-in-the-loop architecture** — Human judgment is necessary but must be amortized at design-time. Three modes: design, exception, iteration.
7. **Compiler formalization (World Manifest Compiler)** — The design-time process is not ad hoc; it is a compilation pipeline with a formal input (manifest), a compilation phase (no LLM survives), and deterministic output.
8. **Honest constraints** — Bounded, measurable security. Not perfect. Not probabilistic. Tractable.
9. **Four-layer architecture (current)** — The runtime model is organized as four distinct layers: Layer 0 (Execution Physics — infrastructure impossibility), Layer 1 (Base Ontology — design-time vocabulary), Layer 2 (Dynamic Ontology Projection — runtime context-dependent capability set), Layer 3 (Execution Governance — policy evaluation gateway). This replaces an earlier five-layer formulation and cleanly separates infrastructure constraints from ontology design, from runtime projection, from governance policy. The execution governance gateway is Layer 3 — one component of a four-layer system, not the whole system.

Each step addressed the strongest objection to the previous step. The result is an architecture that is honest about its limitations and specific about its mechanisms.

---

*Agent Hypervisor is a proof-of-concept research project exploring architectural approaches to AI agent security. It does not represent any company's official position.*

*Last updated: February 2026*