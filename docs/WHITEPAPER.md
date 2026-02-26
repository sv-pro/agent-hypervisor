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

This is **ontological security** — not permission-based, but construction-based. Dangerous actions are not prohibited by rules; they are **absent from the world the agent inhabits**.

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

It is a **compiler for secure semantic worlds**.

Comparable to: Infrastructure-as-Code compilers, type systems, capability-based OS design, and classical hypervisors — but applied to meaning.

### 4. Runtime Architecture

```
[ Raw Reality ]
       ↓
[ Agent Hypervisor — Virtualization Boundary ]
       ↓
[ Agent (LLM / Planner) — Virtualized World ]
```

The hypervisor intercepts all perception, intercepts all actions, and defines the physics of the agent's world.

#### 4.1 Five-Layer Model

```
Layer 1: Reality Interface        — uncontrolled external world
Layer 2: Virtualization Boundary  — security perimeter (the critical seam)
Layer 3: Universe Definition      — what exists in the agent's world
Layer 4: Intent Processing        — deterministic decision layer
Layer 5: Agent Interface          — agent's perceived reality
```

#### 4.2 Core Mechanisms

**Semantic Events (Perception)**

The agent never receives raw input. It receives structured events:

- `source` — email, web, file, MCP, user
- `trust_level` — trusted / untrusted / tainted
- `capabilities` — what is permitted in this context
- `sanitized_payload` — stripped of hidden instructions

For the agent, "just text" does not exist.

**Intent Proposals (Action)**

The agent cannot act directly. It can only propose an intent:

- `send_email(...)`, `write_file(diff=...)`, `run_tool(...)`, `query_resource(...)`

This is a proposal, not an execution.

**Deterministic World Policy (Physics)**

The hypervisor's policy engine is:

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

These are not restrictions. They are **physics laws** of the agent's world.

#### 4.3 Tool Integration (MCP Model)

Tools connect to the hypervisor, not to the agent:

- MCP tool = virtualized device
- Schema = device descriptor
- Capability = permission model
- Policy = access control + physics

Adding a tool does not change the agent, does not complicate the architecture, does not reduce determinism.

#### 4.4 The Acid Test

If you can write a unit test:

```
untrusted input → propose external action → denied
tainted data    → attempt export          → impossible
trusted intent  → execution               → allowed
```

…then the hypervisor is deterministic, not an agent, and architecturally sound.

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

**6.3 Defining the "world" is policy, not physics.** The hypervisor claims actions don't exist rather than being forbidden. But the set of "existing" actions must be designed by someone. Too narrow — the agent is useless. Too wide — security is nominal. This is a design problem inheriting all challenges of policy design — merely disguised as "physics."

### 7. The Implication

The hypervisor moves the problem from runtime to design-time and from the agent to the boundary layer, but does not eliminate it. The fundamental difficulty — transforming an unstructured world into a structured ontology — remains, and the boundary is precisely where an attacker will probe for gaps.

This does not make the architecture useless — it genuinely narrows the attack surface. But the claim "ontologically impossible" is too strong for a system whose boundary inevitably contains a fuzzy parser.

The honest claim: **bounded, measurable security** — not perfect, not probabilistic, but deterministic within explicitly defined boundaries.

This honesty is not a weakness. It is the foundation for everything that follows.

---

## Part III — AI Aikido: Using the Opponent's Force

### 8. The Resolution

The weakness identified above has an elegant resolution if we separate **when** intelligence operates from **where** it enforces.

**AI Aikido** is the principle of using LLM capabilities to generate deterministic artifacts rather than to provide runtime decisions. The stochastic system builds the deterministic system. Intelligence works at **design-time**; only its products operate at **runtime**.

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

Given a description of a business process, an LLM generates the set of permitted actions and their schemas, trust relationships between input channels, capability presets per trust level, taint propagation rules, and escalation conditions.

A human reviews, modifies, and commits. The manifest becomes the constitution of the agent's world — written with AI assistance, executed deterministically.

#### 9.3 Adversarial Red-Teaming of Parsers

The same LLM (or a different one) attacks the generated parsers — generates adversarial inputs designed to bypass canonicalization, probes for edge cases in grammar definitions, crafts semantic ambiguity attacks, tests taint propagation boundaries.

The cycle: **generate → attack → patch → re-attack** — all in design-time. The parsers that survive are deployed; the ones that fail are iterated.

#### 9.4 Context-Aware Taint Rules

An LLM analyzes the data flow of a specific application and proposes taint propagation rules: "If source is email and transformation is `summarize`, taint is preserved." "If transformation is `count_words`, taint is cleared." "If three sources are mixed and any is tainted, result is tainted unless transformation is `aggregate_statistics`."

A human approves each rule. The rule becomes a deterministic physics law. The LLM's understanding of semantic transformations informs the rule; the rule itself contains no stochasticity.

### 10. What AI Aikido Does Not Solve

**Coverage completeness.** LLM-generated parsers cover known attack patterns and patterns the LLM can anticipate. An attacker may find a pattern absent from design-time analysis. However, this is now a manageable engineering problem — parsers can be iterated, adversarial testing automated, coverage expanded incrementally.

**Semantic ambiguity.** "Send the report to Alex" remains ambiguous regardless of design-time effort. AI Aikido can generate the policy rule, but the **correctness** of that rule is a human judgment.

**Adaptation latency.** New attack type → new parser needed → LLM generates → testing → deployment. Faster than manual authoring, but not instantaneous. The gap is finite and measurable, unlike the infinite gap of hoping a runtime probabilistic filter catches an unknown pattern.

---

## Part IV — The World Manifest Compiler

### 11. Agent Hypervisor as a Compiler

Agent Hypervisor is not primarily a runtime policy engine. It is a **design-time compiler** that transforms human + LLM semantic intent into deterministic runtime physics.

The compilation pipeline:

```
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

**Action Ontology** — the complete set of actions the agent can propose, with typed schemas. Actions not in the ontology do not exist. The agent cannot formulate intent for them because they are absent from its world definition.

**Trust Model** — trust channels (user, email, web, file, MCP), trust levels per channel, and rules for trust propagation through transformations. Trust is a property of the channel, not the content.

**Capability Matrix** — which capabilities are available at which trust levels. A matrix, not a list of rules. Capabilities define what is physically possible, not what is permitted.

**Taint Propagation Rules** — deterministic rules for how contamination spreads through data transformations. Each rule specifies: source trust level × transformation type → output taint status. These are the thermodynamic laws of the agent's world.

**Escalation Conditions** — explicit boundaries where the system transitions from deterministic decision to human review. Defined narrowly: the goal is to minimize runtime escalation through comprehensive design-time coverage.

**Provenance Schema** — how origin metadata propagates through the system. Every object carries its lineage. Critical for continuous learning safety: only data with verified provenance enters the learning loop.

### 13. The Compilation Phase

The compiler transforms the World Manifest into executable runtime artifacts:

| Manifest Element        | Compiled Artifact                      |
| ----------------------- | -------------------------------------- |
| Action ontology         | Validated JSON Schemas + intent parser |
| Trust model             | Deterministic trust assignment tables  |
| Capability matrix       | Static capability lookup engine        |
| Taint propagation rules | Taint propagation matrices             |
| Escalation conditions   | Threshold evaluators                   |
| Provenance schema       | Provenance chain validators            |

**No LLM survives this phase.** The output is pure deterministic code — lookup tables, state machines, validators. Every compiled artifact is unit-testable. Every decision is reproducible.

### 14. Runtime Execution

At runtime, the compiled artifacts execute without stochasticity:

1. Raw input arrives at the virtualization boundary
2. Compiled canonicalizer strips known attack patterns
3. Trust assignment table maps source → trust level
4. Taint propagation matrix computes contamination status
5. Capability lookup determines available actions
6. Agent proposes an intent (structured JSON only)
7. Deterministic policy engine evaluates: `allow` | `deny` | `require_approval` | `simulate`
8. Decision is logged with full provenance for audit

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

- World Manifests defining the agent's universe
- Taint propagation rules
- Capability matrices per trust level
- LLM-generated parsers and canonicalizers
- Escalation thresholds

**One design-time decision amortizes across thousands of runtime decisions.** This is analogous to writing a constitution: expensive to draft, but its cost is amortized across every citizen and every moment of governance.

#### 16.2 Runtime Human — Exception, Not Rule

The `require_approval` decision is an **escape hatch** for cases that design-time did not fully cover. It is not the primary path; it is the pressure relief valve.

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

```
Traditional HITL:    Cost = O(n)      per runtime decision
Design-Time HITL:    Cost = O(log n)  per design iteration covering n decisions
```

As the system matures, the share of `require_approval` decisions trends toward zero, deterministic coverage trends toward completeness, and human effort concentrates on novel edge cases rather than routine decisions.

This is precisely the model that made classical hypervisors viable: VMware engineers did not sit beside every VM. They designed isolation rules once, and VMs scaled without human intervention.

### 18. The Four-Phase Cycle

```
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

**Design:** Human + LLM co-create the World Manifest. LLM generates action schemas, trust policies, taint rules, canonicalization logic. Human reviews and commits.

**Compile:** The World Manifest Compiler transforms the manifest into deterministic artifacts — policy tables, JSON schemas, taint matrices, capability graphs. No LLM survives this phase. All artifacts are unit-testable.

**Deploy:** Runtime executes purely deterministic compiled artifacts. No LLM on the critical path. No human in the loop. Decisions are reproducible and auditable.

**Learn:** Runtime logs accumulate. Escalation patterns emerge. Coverage gaps become visible. Metrics quantify deterministic coverage vs. exception rate.

**Redesign:** Human reviews patterns. LLM generates updated manifest elements — new parsers, refined rules, expanded action ontologies. Adversarial testing validates. The manifest is recompiled. The cycle repeats with higher coverage.

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

The architecture must be proven executable, not metaphorical. The minimal viable proof consists of:

**20.1 World Manifest Format**

A YAML-based manifest defining:

```yaml
# Example: minimal World Manifest
version: "1.0"
name: "email-assistant-world"

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

trust_channels:
  user:    { level: trusted,   default_caps: [read, internal_write, external_side_effects] }
  email:   { level: untrusted, default_caps: [read] }
  web:     { level: untrusted, default_caps: [read] }

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

escalation:
  - condition: "action.type == external_side_effect AND trust < trusted"
    decision: require_approval

provenance:
  track: true
  learning_gate: "provenance.verified == true"
```

**20.2 Compiler**

A compiler that transforms the manifest into:

- Deterministic policy lookup tables
- JSON Schema validators for each action
- Taint propagation state machine
- Capability resolution engine
- Unit-testable rule set

**20.3 Runtime Engine**

A deterministic engine that:

- Accepts structured intent proposals (JSON)
- Evaluates against compiled artifacts
- Returns: `allow` | `deny` | `require_approval` | `simulate`
- Logs every decision with full provenance

**20.4 Test Suite**

Unit tests proving invariant enforcement:

```
TEST: untrusted input → external action → DENIED (TaintContainmentLaw)
TEST: tainted data → export attempt → IMPOSSIBLE (physics)
TEST: trusted user intent → allowed action → ALLOWED
TEST: same manifest + same input → same decision (determinism)
TEST: action not in ontology → cannot be proposed (ontological security)
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

Each step addressed the strongest objection to the previous step. The result is an architecture that is honest about its limitations and specific about its mechanisms.

---

*Agent Hypervisor is a proof-of-concept research project exploring architectural approaches to AI agent security. It does not represent any company's official position.*

*Last updated: February 2026*