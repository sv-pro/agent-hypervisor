# THREAT_MODEL.md — Agent Hypervisor

*Draft v0.1 — March 2026*

---

## 1. Purpose

This document defines the threat model for the Agent Hypervisor architecture. It establishes:

- Where the virtualization boundary is and what it protects
- Which inputs are trusted and which are not
- Which threats are in scope and how the architecture addresses them
- Which threats are explicitly out of scope and why

A reader should be able to point to the exact boundary and trust assumptions after reading this document. Constraints are stated as explicitly as capabilities.

---

## 2. The Virtualization Boundary

The virtualization boundary is the **single point through which all external signals must pass before reaching the agent**. It corresponds to Layer 1 (Input Boundary) in the five-layer architecture.

```text
┌──────────────────────────────────────────────────┐
│                  External World                  │
│  (emails, web pages, files, APIs, MCP servers,   │
│   other agents, user messages)                   │
└────────────────────────┬─────────────────────────┘
                         │
              ═══════════▼═══════════
              ║  VIRTUALIZATION     ║  ← THE BOUNDARY
              ║  BOUNDARY           ║
              ║  (Layer 1)          ║
              ═══════════╪═══════════
                         │
                         │  Only Semantic Events cross downward
                         │  Only Intent Proposals cross upward
                         ▼
┌──────────────────────────────────────────────────┐
│                 Agent's World                    │
│  (Layers 2–3: Universe Definition + Interface)   │
└──────────────────────────────────────────────────┘
                         │
              ═══════════▼═══════════
              ║  EXECUTION          ║  ← SECOND BOUNDARY
              ║  BOUNDARY           ║
              ║  (Layer 5)          ║
              ════════════════════════
                         │
                         ▼
              External effects (tool calls, API writes)
```

**Critical properties of the boundary:**

- **Everything passes through it.** No raw input reaches the agent. No agent output reaches the world without evaluation.
- **It is deterministic.** The same input produces the same Semantic Event, always.
- **It is the only place taint is assigned.** Once assigned at Layer 1, taint propagates automatically through all downstream operations.
- **It is not the agent.** The boundary contains no LLM. It operates on rules compiled from the World Manifest.

---

## 3. Trust Channels

Every input to the system arrives through one of the following trust channels. Trust is a property of the **channel**, not the content.

| Channel          | Trust Level   | Default Capabilities                            | Notes                                                                       |
| ---------------- | ------------- | ----------------------------------------------- | --------------------------------------------------------------------------- |
| `user`           | `TRUSTED`     | read, internal_write, external_side_effects     | Direct human interaction. Highest trust by default.                         |
| `email`          | `UNTRUSTED`   | read only                                       | Fully attacker-controlled. All content is tainted at entry.                 |
| `web`            | `UNTRUSTED`   | read only                                       | Attacker-controlled. Includes fetched pages, scraped data, RSS.             |
| `file`           | `SEMI_TRUSTED` | read, internal_write (no external side effects) | Trust depends on provenance of the file. Default: semi-trusted.            |
| `MCP`            | `SEMI_TRUSTED` | tool-specific, defined in World Manifest        | Tool outputs are structured but may contain attacker-influenced data.       |
| `agent-to-agent` | `UNTRUSTED`   | read only (no transitive trust escalation)      | Another agent is not trusted by construction — it may itself be compromised.|

**Trust propagation rule:** Trust level cannot be upgraded by the agent. Only the World Manifest, reviewed and committed at design-time, defines trust levels. An `UNTRUSTED` input cannot produce a `TRUSTED` Semantic Event regardless of its content.

**Taint assignment rule:** Any input arriving through an `UNTRUSTED` channel is automatically tainted. `SEMI_TRUSTED` inputs are tainted unless the World Manifest explicitly specifies a sanitization rule for the specific transformation.

---

## 4. In-Scope Threats

### 4.1 Prompt Injection

**Description:** An attacker embeds instructions in content the agent processes (email body, web page, file contents, tool output). The agent treats attacker-controlled data as instructions.

**Why it is architecturally predictable:** In raw reality, the agent receives unmediated text. There is no structural distinction between data and instruction at the input boundary.

**Hypervisor mitigation:**
- All `UNTRUSTED` and `SEMI_TRUSTED` inputs are transformed into Semantic Events with `sanitized_payload` — known injection patterns are stripped at Layer 1.
- The agent never sees raw text. It sees a structured object with explicit `trust_level` and `taint` fields.
- Even if injection patterns survive sanitization (semantic gap), the Semantic Event's `trust_level` propagates to any derived Intent Proposal — a tainted proposal cannot reach Layer 5 (Execution Boundary) for privileged actions.

**Residual risk:** Semantically ambiguous injections that are not recognized as injections by the Layer 1 classifier. See Section 6 (Out of Scope).

---

### 4.2 Tainted Egress (Data Exfiltration)

**Description:** An attacker causes the agent to send tainted data (e.g., contents of a private document) to an external destination controlled by the attacker, using a whitelisted tool (e.g., `send_email`).

**Why it is architecturally predictable:** In raw reality, taint is not tracked. A tool call with tainted arguments is indistinguishable from a legitimate call.

**Hypervisor mitigation:**
- Taint propagates automatically from untrusted inputs through all derived objects.
- The Taint Containment Law (enforced at Layer 4): a tainted object cannot reach Layer 5 without an explicit sanitization gate defined in the World Manifest.
- This is enforced as a physics law, not a policy check — the route from tainted data to external action does not exist in the architecture.

**Residual risk:** Incorrect taint propagation rules that fail to propagate taint through a specific transformation (undertainting). See Section 6.

---

### 4.3 Tool Abuse

**Description:** An agent is manipulated into calling legitimate tools in ways that cause unintended harm — deleting files, sending unauthorized emails, triggering API operations.

**Why it is architecturally predictable:** In raw reality, the agent has direct tool access. A compromised agent and a cooperative agent are indistinguishable from the tool's perspective.

**Hypervisor mitigation:**
- Tools are not accessible to the agent directly. The agent produces Intent Proposals; the hypervisor evaluates them.
- The World Manifest defines which tools exist in the agent's universe (Layer 2: Universe Definition). Tools not in the manifest do not exist — the agent cannot formulate intent to call them.
- The Deterministic World Policy at Layer 4 evaluates every Intent Proposal against: action type, trust level, taint status, reversibility classification, and budget limits.
- Irreversible actions (e.g., `send_email`, `delete_file`) require `require_approval` or are `deny`ed for untrusted-origin proposals.

**Residual risk:** World Manifest is too permissive — tools that should be restricted are included in the agent's universe. This is a design-time mistake, not a runtime bypass.

---

### 4.4 Poisoned Tool Outputs (MCP Injection)

**Description:** A malicious MCP server (or a legitimate MCP server returning attacker-influenced data) returns a payload that injects instructions into the agent's context through tool output.

**Why it is architecturally predictable:** MCP tool outputs are raw text. If the agent processes tool outputs the same way it processes user instructions, tool outputs are a prompt injection vector.

**Hypervisor mitigation:**
- MCP tool outputs arrive through the `MCP` trust channel — classified as `SEMI_TRUSTED`.
- Tool outputs are transformed into Semantic Events before reaching the agent. The `sanitized_payload` field strips known injection patterns.
- The `trust_level` of the Semantic Event reflects the tool's trust classification in the World Manifest, not the content of its output.
- Tool outputs from untrusted or unknown MCP servers are treated as `UNTRUSTED`.

**Residual risk:** Sophisticated semantic injections in tool outputs that pass the Layer 1 classifier. Trust level of the Semantic Event limits the damage: a `SEMI_TRUSTED` tool output cannot produce a `TRUSTED` Intent Proposal.

---

### 4.5 Memory Poisoning (Surrogate Injection)

**Description:** An attacker causes malicious content to be written to the agent's persistent memory. In future sessions, the agent retrieves and acts on the poisoned memory as if it were a trusted prior context.

**Why it is architecturally predictable:** In raw reality, memory writes are unattributed. A poisoned memory entry is indistinguishable from a legitimate one.

**Hypervisor mitigation:**
- All memory writes are attributed (Provenance Invariant: I-2). Every memory object carries its origin channel and trust level.
- Memory trust zones are segmented: learning memory, operational memory, and user memory are separate with different export policies.
- A memory object written from an `UNTRUSTED` source carries the taint and trust level of that source — it cannot be promoted to trusted context without an explicit sanitization gate.
- The `learning_gate` in the World Manifest (see WHITEPAPER Section 12) requires `provenance.verified == true` before a memory entry enters the learning loop.

**Residual risk:** The learning gate depends on provenance verification being correctly implemented. If provenance is incorrectly attributed at Layer 1, a poisoned memory entry may enter the learning loop with a falsified origin. This is the most critical residual risk in the architecture.

---

## 5. Critical Path

The critical path is the sequence of operations that must remain deterministic and LLM-free for the security guarantees to hold:

```text
Raw input
  → [Layer 1] Trust classification + taint assignment + injection stripping
  → Semantic Event (structured, attributed, sanitized)
  → [Layer 3] Agent perceives Semantic Event
  → Agent produces Intent Proposal (structured JSON)
  → [Layer 4] Deterministic World Policy evaluation:
      - Is the action in the World Manifest?
      - Is the trust level sufficient?
      - Is the data tainted?
      - Is the action reversible?
      - Is the budget exhausted?
  → decision: allow | deny | require_approval | simulate
  → [Layer 5] If allowed: tool invocation + immutable audit log
```

**No LLM appears in this path.** The agent (LLM) operates exclusively in Layer 3. It perceives Semantic Events and proposes intents. It does not participate in trust classification, taint propagation, policy evaluation, or execution.

**The path is unit-testable end-to-end** without mocking the agent. See CONCEPT.md Section 8 (Conformance test pattern).

---

## 6. Out of Scope and Explicit Constraints

### 6.1 Semantic Ambiguity at the Boundary

**What is out of scope:** The hypervisor cannot deterministically resolve genuine semantic ambiguity. "Send this report to Alex" may be a legitimate user request or a socially engineered instruction embedded in a document. The Layer 1 classifier handles known injection patterns; it cannot handle all possible semantic framings of an attack.

**Implication:** The attack surface is not zero — it is bounded to the Layer 1 classifier's coverage. Novel injection framings may pass Layer 1 but are then constrained by the trust level of the Semantic Event.

### 6.2 Finite Manifest Completeness

**What is out of scope:** The World Manifest covers what was anticipated at design-time. A novel attack that exploits an action or capability not anticipated in the manifest may find an unguarded path.

**Implication:** The manifest must be iterated. The AI Aikido cycle (design → compile → deploy → learn → redesign) is the mechanism for expanding coverage. This is an engineering problem with a finite improvement path, not an unbounded probabilistic failure mode.

### 6.3 Delayed Adaptation

**What is out of scope:** The system does not adapt to new attack patterns at runtime. New attack type → manifest redesign → recompilation → redeployment. This cycle takes time.

**Implication:** There is a latency window between discovery of a new attack pattern and deployment of a updated manifest. This window is finite and measurable, unlike runtime probabilistic defenses where the adaptation latency is effectively unbounded.

### 6.4 Host System Compromise

**What is out of scope:** If the host operating system, the hypervisor process itself, or the compilation pipeline is compromised, the guarantees of this document do not apply. Agent Hypervisor operates at the semantic layer — it does not address infrastructure-level attacks.

### 6.5 World Manifest Design Errors

**What is out of scope:** A poorly designed World Manifest produces a poorly secured world. If the manifest grants excessive capabilities, misclassifies trust channels, or omits necessary taint rules, the resulting system is insecure by construction.

**Implication:** Security is a property of the manifest, not of the runtime alone. Human review of the manifest at design-time is a required step, not an optional one.

### 6.6 LLM Model Vulnerabilities

**What is out of scope:** Vulnerabilities in the underlying LLM itself — jailbreaks, model-level adversarial attacks, or alignment failures. The hypervisor controls what the agent perceives and what it can cause — it does not control what the agent thinks.

**Implication:** A jailbroken agent can produce malicious Intent Proposals. Those proposals are still evaluated by the Deterministic World Policy. The hypervisor's security properties hold even when the agent behaves adversarially (Containment Independence, Factor 12 of the 12-Factor Agent).

---

## 7. Bounded Security Claim

Agent Hypervisor does not claim perfect security. It claims **bounded, measurable security**:

- The attack surface has an explicit shape: Layer 1 (Input Boundary) and Layer 5 (Execution Boundary) are the only contact points with external reality.
- Every successful attack must either pass Layer 1 undetected or exploit a misconfigured World Manifest.
- Both attack surfaces are auditable, testable, and improvable through iteration.
- The failure mode is **engineering debt** (incomplete manifest, insufficient classifier coverage), not **probabilistic drift** (unknown bypass rates against runtime filters).

This is a strictly better security posture than probabilistic defenses — not because the residual risk is smaller in every case, but because the residual risk is **known**, **bounded**, and **addressable**.

---

*See [WHITEPAPER.md](docs/WHITEPAPER.md) for the full architectural specification.*
*See [CONCEPT.md](CONCEPT.md) for the five-layer architecture and conformance invariants.*
*See [docs/GLOSSARY.md](docs/GLOSSARY.md) for term definitions.*
