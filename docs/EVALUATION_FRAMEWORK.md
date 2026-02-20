# Evaluation Framework: Crutch, Workaround, or Bridge?
### How to assess AI agent security tools against the architectural root cause

*Part of the Agent Hypervisor project.*
*https://github.com/sv-pro/agent-hypervisor*

---

Most AI agent security tools are useful. The question is not whether they help — it is what they help with, and whether that help scales to the actual threat model.

This framework provides a vocabulary for honest evaluation. Three categories, ordered by strategic value.

---

## The Three Categories

### 🔴 Crutch

A crutch treats symptoms. It does not change the architecture that produces the vulnerability. It operates probabilistically on the surface of the problem.

**Characteristics:**
- Intercepts or filters after the fact
- Bypassable under adaptive attacks (90%+ bypass rate in research)
- Does not survive continuous learning scenarios
- Provides false confidence at the cost of real understanding
- Cannot be unit-tested for security guarantees

**When to use:** Never, if a better option exists. As last resort only.

**Strategic verdict:** Buying time, not buying safety.

---

### 🟡 Workaround

A workaround solves the immediate problem without solving the root cause. It is production-ready, deployable today, and provides partial protection. It buys time and reduces risk in the short term.

**Characteristics:**
- Production-ready, deployable now
- Partial protection (30–70% of attack surface)
- Does not address architectural root cause
- Buys time for a proper solution
- Has a clear migration path to something better

**When to use:** When you need security today and are building toward architecture tomorrow.

**Strategic verdict:** Responsible tactical choice. Not a permanent answer.

---

### 🟢 Bridge

A bridge introduces architectural thinking. It may not be a complete solution, but it establishes the right abstractions, teaches the right patterns, and is composable with a proper architectural approach.

**Characteristics:**
- Introduces correct abstractions (trust levels, provenance, intent separation)
- Has a clear migration path to full architectural solution
- Teaches the right mental model
- Composable with future systems
- Validates the problem space correctly

**When to use:** As a foundation layer. Build on top of it.

**Strategic verdict:** The right investment direction.

---

## Classification Criteria

| Criterion                          | Crutch | Workaround | Bridge                    |
| ---------------------------------- | ------ | ---------- | ------------------------- |
| Addresses root cause               | No     | Partially  | Conceptually yes          |
| Deterministic guarantees           | No     | No         | Partial                   |
| Bypass rate under adaptive attacks | >70%   | 30–70%     | <30%                      |
| Survives continuous learning       | No     | No         | Yes (if provenance-aware) |
| Unit-testable security properties  | No     | Partially  | Yes                       |
| Correct abstraction level          | No     | No         | Yes                       |
| Migration path to architecture     | No     | Possible   | Yes                       |

---

## Applied Classifications

### Rebuff (Protect AI)
**Type:** Prompt injection detection via canary tokens and heuristics
**Approach:** Detect injection attempts before they reach the model

**Classification: 🔴 Crutch**

Detection is not prevention. The tool operates on the surface of raw text, after the agent has already been exposed to untrusted input. Bypass rate exceeds 90% under adaptive attacks. No provenance tracking. No architectural change. Provides a signal, not a guarantee.

*What to use instead today:* Input classification with trust tagging (30 min to implement, 20–30% protection, correct abstraction direction).

---

### Guardrails AI
**Type:** Output validation framework
**Approach:** Define validators, check outputs post-generation

**Classification: 🔴 Crutch**

Reactive by design. The agent has already reasoned over dangerous input by the time output validation runs. No input virtualization. No memory protection. Useful for compliance (PII detection), not for architectural security. Treats the symptom at the wrong end of the pipeline.

*What to use instead today:* Combine with input classification. Guardrails AI as output layer + provenance-tagged inputs = Workaround territory.

---

### IronClaw (NearAI)
**Type:** Security wrapper for LLM API calls
**Approach:** Input validation, output filtering, rate limiting, audit logging

**Classification: 🟡 Workaround**

Production-ready. Drop-in replacement. Comprehensive checks. Provides real protection against basic attacks (60–70% coverage). Does not address provenance, does not survive continuous learning, cannot make security guarantees. But it is deployable today and better than nothing.

*Migration path:* Input validation layer → Semantic Event construction. Rate limiting → Budget constraints. Audit logging → Immutable provenance log.

---

### LangChain Security Toolkit
**Type:** Framework-level security features
**Approach:** Optional sandboxing, memory isolation, tool restrictions

**Classification: 🟡 Workaround (if used properly)**

The key word is "optional". Developers must actively enable security features. No systematic virtualization. No provenance by default. But when used intentionally, it provides correct abstractions at the framework layer and integrates naturally with the agent's execution model.

*Migration path:* LangChain tool abstraction → Intent Proposal layer. Memory isolation → Segmented memory with trust zones.

---

### NVIDIA NeMo Guardrails
**Type:** Programmable guardrails with policy language
**Approach:** Define conversation flows and policies in YAML

**Classification: 🟢 Bridge (partial)**

The most architecturally interesting of the current generation. Introduces policy as a first-class concept. Structured safety approach. The YAML policy language is a step toward deterministic world definition. Still probabilistic in enforcement, still complex to configure correctly. But it establishes the right mental model: safety is a policy, not a prompt.

*Migration path:* NeMo policy language → World Policy (Layer 4). Conversation flow control → Intent mediation.

---

### Lakera Guard (Commercial)
**Type:** Enterprise prompt injection defense API
**Approach:** Detection service, continuously updated

**Classification: 🟡 Workaround (enterprise-grade)**

Production-grade, continuously updated, enterprise support. Better detection rates than open-source alternatives. Still detection-based, still bypassable, still operates at the wrong abstraction level. Market signal: enterprise is willing to pay for this problem. Validates the threat model without solving the root cause.

*Strategic note:* Lakera's existence proves the market. Agent Hypervisor's existence proposes the architecture.

---

## The Pattern

Every tool in this landscape operates **after** the agent has been exposed to raw reality. The best ones (NeMo, IronClaw) introduce fragments of the right abstractions. None of them change the fundamental architecture.

The question is not "which crutch is best?" The question is "what does the world look like when we stop needing crutches?"

That question is what Agent Hypervisor tries to answer.

---

## Applying This Framework

For each tool you evaluate, ask:

1. **At what point does this intervene?** Before perception, during reasoning, or after output?
2. **Is the guarantee probabilistic or deterministic?** Can it be unit-tested?
3. **Does it introduce correct abstractions?** Trust levels, provenance, intent separation?
4. **Does it survive continuous learning?** If the agent learns from contaminated data, does this help?
5. **What is the migration path?** Does using this tool make the architectural solution easier or harder?

If the answer to questions 2–5 is consistently "no" — you have a crutch.

---

*Architectural draft. Not a product comparison. Classifications are based on published research and public documentation.*
*Feedback and corrections welcome: https://github.com/sv-pro/agent-hypervisor/discussions*