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

## Capability Matrix

A table defined in the World Manifest that maps trust levels to permitted action types. For each trust level (`TRUSTED`, `SEMI_TRUSTED`, `UNTRUSTED`), the capability matrix specifies which categories of actions are available (e.g., `read`, `internal_write`, `external_side_effects`). The matrix is evaluated at Layer 4 (World Policy) on every Intent Proposal.

Example: a `SEMI_TRUSTED` input can produce intents for `read` and `internal_write`, but not `external_side_effects`. An `UNTRUSTED` input can produce intents for `read` only.

---

## Capability Rendering

The design-time transformation of raw, general-purpose tools into role-specific, parameter-constrained capabilities. `send_email(to, body)` becomes `send_report_to_security(body)`. The raw tool is not restricted — it is replaced. The concept of "arbitrary recipient" becomes non-representable in the agent's world.

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

## Escalation Condition

A rule defined in the World Manifest that triggers a `require_approval` decision instead of an automatic `allow` or `deny`. Escalation conditions specify when a human must explicitly approve an Intent Proposal before execution proceeds — typically for irreversible actions, high-consequence operations, or actions on sensitive targets.

Escalation conditions are evaluated at Layer 4 (World Policy) as part of the deterministic policy evaluation. They are defined at design-time in the manifest; the runtime does not invent new escalation triggers.

---

## Intent Proposal

A structured request from an agent describing what action it wants to perform and on what target. The agent proposes; the Hypervisor decides whether the intent can exist as a consequence in the virtual world. Agents never execute directly.

---

## L∞ Layer

Semantic security layer in the L∞ stack — the agent-level analogue of a WAF.

---

## Ontology Fit

The property that an agent's available abstractions, actions, and categories match its intended role exactly — no more, no less. Surplus capability is surplus risk. An agent with tools beyond its role has the wrong ontology. Intelligence without ontology is instability.

---

## Ontological Boundary

A security boundary defined by existence, not permission. Traditional security asks "are you allowed to do X?" An ontological boundary asks "does X exist in your world?" If it doesn't exist, there is nothing to bypass.

---

## Ontological Security

Security through non-existence of dangerous actions, not through prohibition.

---

## Perception-Bounded World

The foundational model: an agent does not operate in the real world — it operates in its field of perception. The agent's world is defined by its input channels, available tools, accessible memory, and representable abstractions. If something is not perceivable, it does not exist for the agent. If something is not actionable, it cannot happen. The World Manifest is the formal specification of the perception boundary. See [concepts/perception_bounded_world.md](concepts/perception_bounded_world.md).

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

A label attached to data indicating it originated from an untrusted source. Tainted data cannot cross specified boundaries (e.g., the Execution Boundary at Layer 5) without an explicit sanitization gate defined in the World Manifest. Taint is enforced as a physics law, not a permission check.

---

## Taint Propagation

The automatic forwarding of taint labels through data transformations. If a tainted object is read, concatenated, summarized, or otherwise processed, the derived object inherits the taint. Taint propagation is defined by taint rules in the World Manifest and compiled into a state machine at design-time.

Example: an email body arrives tainted → the agent summarizes it → the summary is also tainted → a `send_email` intent using the summary is blocked at Layer 4 (Taint Containment Law).

The purpose of propagation is to close the gap where an attacker's data moves through intermediate steps before reaching a privileged action.

---

## Universe

The definition of what exists in the agent's virtual world: which objects are accessible, which actions are possible, and which physics laws govern behavior. The Hypervisor instantiates a Universe at startup based on the policy configuration.

---

## Virtualization Boundary

The point at which raw reality inputs are transformed into Semantic Events. Injection stripping, trust classification, and taint tagging all happen here. Nothing from raw reality enters the agent's world without passing through this boundary.

---

## Virtualized Device

An abstraction of an external resource (tool, API, file system, network endpoint) that the agent interacts with through the hypervisor rather than directly. The agent perceives a virtualized device as an available capability in its universe; the hypervisor translates approved intents into actual invocations on the underlying resource.

Virtualized devices are the agent-facing representation of real tools. They enforce the same ontological boundary as the rest of the architecture: a tool not defined as a virtualized device in the World Manifest does not exist in the agent's universe.

---

## World State

Mutable state tracked by the Hypervisor across a session — for example, how many files have been opened. Physics laws can reference world state to enforce cumulative limits.

---

## World Manifest

A YAML document authored at design-time (with human review) that formally defines what exists in an agent's universe. The manifest is the single source of truth for the World Policy. It specifies:

- **Action ontology** — which tools and action types exist in this world
- **Trust model** — which input channels exist and their default trust levels
- **Capability matrix** — which capabilities are available at each trust level
- **Taint rules** — how taint propagates through specific transformations
- **Escalation conditions** — when to require human approval before execution
- **Provenance schema** — how data origin is tracked through the system
- **Budget limits** — session-level resource constraints (action counts, token budgets, etc.)

The manifest is compiled by the World Manifest Compiler into deterministic runtime artifacts. The LLM is used at design-time to help author the manifest; no LLM is involved at runtime.

---

## World Manifest Compiler

The compilation phase that transforms a manifest into deterministic runtime artifacts — policy tables, schemas, taint matrices.

---

*See [WHITEPAPER.md](WHITEPAPER.md) for the foundational definitions and [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical specification.*
