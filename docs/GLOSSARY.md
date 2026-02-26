# Glossary

Key terms used in Agent Hypervisor documentation and code.

---

## AI Aikido

Principle of using LLM capabilities at design-time to generate deterministic runtime artifacts.

---

## Agent

An AI system (LLM-based or otherwise) that perceives inputs and proposes actions to achieve goals. In the Agent Hypervisor model, an agent never executes actions directly — it only proposes intents.

---

## Architectural Predictability

The property that a class of attacks is not a surprise exploit but an inevitable consequence of the current system architecture. Prompt injection is architecturally predictable because agents cannot structurally distinguish trusted instructions from untrusted data. See [docs/VULNERABILITY_CASE_STUDIES.md](VULNERABILITY_CASE_STUDIES.md).

---

## Construction-Time Safety

Safety that is guaranteed by how the system is built, as opposed to detection-time safety (blocking attacks after they are identified). If an action is impossible by construction, there is nothing to detect or block.

---

## Bounded Security

Security whose limits are explicit, measurable, and improvable — as opposed to probabilistic security whose failure rate is unknown.

---

## Deterministic World Policy

A set of rules — "physics laws" — that the Hypervisor enforces on every intent proposal. The key property is determinism: the same intent + policy + world state always produces the same decision. This makes safety properties formally unit-testable.

---

## Compiled Physics

The deterministic runtime artifacts produced by the World Manifest Compiler — the "laws of nature" governing the agent's world.

---

## Hypervisor

The deterministic virtualization layer between the Agent and Reality. Responsible for:

1. Virtualizing inputs (raw reality → Semantic Events)
2. Evaluating intent proposals (applying World Physics)
3. Materializing approved consequences (touching reality only when safe)

Analogous to a classical OS hypervisor, which virtualizes CPU and RAM. The Agent Hypervisor virtualizes meaning and action.

---

## Design-Time HITL

Human-in-the-loop model where human judgment is amortized through design-phase review rather than runtime intervention.

---

## Intent Proposal

A structured request from an agent describing what action it wants to perform and on what target. The agent proposes; the Hypervisor decides whether the intent can exist as a consequence in the virtual world. Agents never execute directly.

---

## L∞ Layer

Semantic security layer in the L∞ stack — the agent-level analogue of a WAF.

---

## Ontological Boundary

A security boundary defined by existence, not permission. Traditional security asks "are you allowed to do X?" An ontological boundary asks "does X exist in your world?" If it doesn't exist, there is nothing to bypass.

---

## Ontological Security

Security through non-existence of dangerous actions, not through prohibition.

---

## Physics Law

A deterministic rule enforced by the Hypervisor as a law of the virtual world — not as a suggestion, a filter, or a policy that can be bypassed. Examples:

- **Taint Containment Law**: Untrusted-tainted data cannot cross the external boundary.
- **Provenance Law**: Memory writes from untrusted sources cannot target execution memory.
- **Reversibility Law**: Side effects of actions are staged before materialization.

---

## Provenance

The tracked origin and handling history of a piece of data. The Hypervisor tags all data with its provenance at the virtualization boundary and propagates this tag through data flows. Provenance enables physics laws to apply correctly regardless of how data was transformed.

---

## Reality

The actual external world: file systems, networks, databases, external APIs. Agents in the Agent Hypervisor model never directly access reality. Only the Hypervisor's materialization layer touches reality, and only for approved, staged intents.

---

## Semantic Event

A virtualized input event created by the Hypervisor from raw reality input. A Semantic Event carries:

- **source**: where the input came from (e.g., `external_email`)
- **trust_level**: classification of the source (`TRUSTED`, `UNTRUSTED`, `INTERNAL`)
- **taint**: propagated sensitivity classification
- **capabilities**: what actions are permitted based on this event's context
- **sanitized_payload**: the content with injection patterns stripped

The agent perceives only Semantic Events — never raw reality.

---

## Taint

A label attached to data that propagates through data flows and prevents the data from crossing specified boundaries. Tainted data (e.g., from an untrusted email) cannot be sent to external destinations, even through whitelisted tools. Taint is enforced as a physics law, not a permission check.

---

## Universe

The definition of what exists in the agent's virtual world: which objects are accessible, which actions are possible, and which physics laws govern behavior. The Hypervisor instantiates a Universe at startup based on the policy configuration.

---

## Virtualization Boundary

The point at which raw reality inputs are transformed into Semantic Events. Injection stripping, trust classification, and taint tagging all happen here. Nothing from raw reality enters the agent's world without passing through this boundary.

---

## World State

Mutable state tracked by the Hypervisor across a session — for example, how many files have been opened. Physics laws can reference world state to enforce cumulative limits.

---

## World Manifest

Formal definition of what exists in an agent's universe — actions, trust model, capabilities, taint rules, escalation conditions.

---

## World Manifest Compiler

The compilation phase that transforms a manifest into deterministic runtime artifacts — policy tables, schemas, taint matrices.

---

*See [WHITEPAPER.md](WHITEPAPER.md) for the foundational definitions and [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) for the full technical specification.*
