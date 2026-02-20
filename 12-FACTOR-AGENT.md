# The 12-Factor Agent
### A methodology for building secure agentic AI systems

*Draft v0.1 — February 2026*

---

Agentic systems fail in predictable ways. Not because the models are too powerful, but because the architectures that host them were inherited from a different era — one where software executed instructions, not inferred them.

The root failure is architectural: agents are placed into raw reality. They receive unmediated input, write to shared memory, and invoke tools with immediate effect. In this environment, every input is a potential instruction, every memory write is a potential corruption, and every tool call is a potential weapon. The vulnerabilities that follow — prompt injection, memory poisoning, tool abuse — are not bugs. They are the mathematically inevitable consequence of this design. **We are surprised by gravity.**

The 12-Factor Agent is a set of architectural principles for systems that must remain secure regardless of what the model does. Not how the model thinks, but how the world it inhabits is constructed. **The factors do not constrain the agent's reasoning. They constrain its physics.**

---

## I. Perception Layer
*Factors 1–4*

*The security boundary begins before reasoning occurs. An agent cannot be compromised by what it cannot perceive. These factors ensure that the agent's sensory input is typed, attributed, and hygienic by default.*

### 1. Virtualized Reality
The agent never interacts with raw reality directly. Every perception passes through a deterministic boundary layer that defines what exists in the agent's world.

*Anti-pattern: agent reads emails, files, or web pages directly.*

### 2. Structured Input
There is no "raw text". Every input is a Semantic Event with source, trust level, provenance, and sanitized payload. The dangerous part is not the content — it is the absence of metadata.

*Anti-pattern: `user_input = request.body`*

### 3. Provenance as Type
Data provenance is part of its type, not a tag you add later. `trusted_user_message` and `untrusted_web_content` are different types even if their string values are identical.

*Anti-pattern: memory without source attribution.*

### 4. Taint by Default
Data from untrusted sources is tainted. Taint propagates through operations automatically. Tainted objects cannot cross the external boundary — not because it is prohibited, but because it is physically impossible by construction.

*Anti-pattern: sanitize-on-exit instead of taint-on-entry.*

---

## II. World Definition
*Factors 5–8*

*The agent inhabits a constructed ontology, not the host operating system. These factors define the physics of that world: what exists, how memory behaves, and how intentions are formed. Security is enforced by the non-existence of unsafe capabilities.*

### 5. Intent, Not Execution
The agent proposes intentions. The environment executes them. These are architecturally separate concerns with separate guarantees. An agent that calls tools directly is an agent without a hypervisor.

*Anti-pattern: `tool.send_email(recipient, body)` called directly by agent.*

### 6. Deterministic Policy
The critical security path contains no LLM. Security decisions are deterministic, reproducible, and unit-testable. The model reasons; the policy decides.

*Anti-pattern: "ask the model if this action is safe".*

### 7. Minimal Universe
The agent can only do what exists in its world. Missing capabilities are ontological impossibilities, not denied permissions. There is a difference between "you cannot" and "it does not exist".

*Anti-pattern: all tools available by default, filtered by policy.*

### 8. Segmented Memory
Memory is divided into trust zones with lifecycle, provenance, and export policy. There is no global mutable context. Learning memory is physically separated from operational memory.

*Anti-pattern: a single unstructured memory blob shared across trust levels.*

---

## III. System Guarantees
*Factors 9–12*

*Regardless of the agent's internal state or alignment, the hosting system must maintain invariants. These factors ensure that even a compromised or adversarially manipulated agent cannot cause irreversible damage to the environment.*

### 9. Reversibility by Default
External actions with irreversible consequences require explicit approval. Everything reversible is default. Everything irreversible is opt-in. The agent cannot cause permanent effects by accident.

*Anti-pattern: `send_email()` without an approval gate.*

### 10. Bounded Autonomy
Agent autonomy exists within its world — defined architecturally, not instructed behaviorally. You cannot teach an agent to be safe. You can build a world where unsafe actions do not exist.

*Anti-pattern: safety through system prompt instructions.*

### 11. Testable Physics
If you cannot write a unit test of the form `untrusted_input → proposed_external_action → denied`, you do not have an architecture. You have a prayer.

*Anti-pattern: "we trust the model not to do bad things".*

### 12. Containment Independence
A compromised agent must not mean a compromised system. Security layers are independent of agent behavior. The system remains safe even when the agent acts adversarially.

*Anti-pattern: security that assumes the agent is cooperative.*

---

*This is an architectural draft, not a product specification. Contributions and critical feedback welcome.*