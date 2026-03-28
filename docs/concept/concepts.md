# Core Concepts

This document defines the foundational concepts of the Agent Hypervisor architecture. Each term is used precisely throughout the codebase and documentation.

---

## Perception Model

An agent's world is bounded by its field of perception — not by physical reality or the full extent of system access.

The perception model has four components:

**Input channels** — the streams of information the agent can observe. What arrives through these channels is the agent's complete knowledge of the world. What does not arrive does not exist.

**Available tools** — the actions the agent can invoke. Tool availability is not a permission check evaluated at invocation time — it is an ontological fact established at compile time. If a tool is not in the manifest, it cannot be invoked because it has no representation.

**Accessible memory** — the context the agent can reference when constructing responses or decisions. Memory that is not accessible does not influence behavior.

**Representable abstractions** — the conceptual vocabulary available to the agent for reasoning and planning. If an action cannot be represented in the agent's capability space, it cannot be planned.

Two consequences follow directly:

> If something is not perceivable, it does not exist.  
> If something is not actionable, it cannot happen.

These are not aspirational constraints. They are engineering facts about a correctly compiled world.

---

## World Manifest

The world manifest is the compiled description of an agent's closed world. It is derived from the workflow definition by the compiler and is fixed before the agent runs.

What the manifest contains:

- the set of tools the agent may invoke
- the parameters each tool may accept
- the resource constraints on each tool (paths, remotes, commands)
- the provenance rules governing how inputs may flow to outputs

What the manifest is not:

- a runtime filter
- a permission system checked at invocation time
- a behavioral heuristic evaluated probabilistically

The manifest is a structural definition. Capabilities outside it have no representation. Enforcement against the manifest is deterministic. **The manifest is the world** — the agent operates inside it, not alongside it.

---

## Capability Rendering

Capability rendering is the process of transforming a world manifest into the agent's actual tool surface — the set of operations the agent can observe and invoke.

The rendered capability surface is minimal by construction. The compiler does not include capabilities that the workflow does not require. This is not conservative filtering — it is the correct minimum.

```
World Manifest  →  Rendered Capability Surface  →  Enforcement Engine
```

From the enforcer's perspective:

- a rendered capability exists and may be invoked, subject to provenance constraints
- a capability absent from the rendering does not exist — the agent cannot form a call to it
- a capability present in the rendering but invoked outside its constraints produces `DENY_POLICY`

**This is construction, not filtering.** A filter receives a request and decides whether to allow it. Capability Rendering constructs the surface before any request is formed. There is nothing for a filter to catch because the request cannot be formed.

---

## Ontology: Roles and Creatures

Ontology is the definition of what entities can exist and what they can do within a world.

In standard software, ontology is implicit — objects have methods, interfaces define contracts. In agentic systems, ontology must be explicit and designed.

**An agent is not a universal actor. It is a role-bound entity.**

A role defines:

- what the agent is in this world
- what actions belong to that role
- what resources the role has access to
- what responsibilities and constraints come with the role

An agent deployed without explicit role-binding has an open ontology. It can construct plans and take actions beyond any intended scope — not because it is malicious, but because nothing in its world defines what it should not be.

> Wrong ontology → wrong behavior.  
> Intelligence without ontology → instability.

The manifest is the ontological definition of the agent's role. It makes the agent a creature that belongs to its world — not a general-purpose actor placed inside it and trusted to stay in bounds.

---

## Step

A Step is the structured representation of an agent action, produced after parsing the LLM output:

```
Step {
  tool:          the action type (e.g. file_read, git_push)
  action:        the operation requested
  resource:      the target of the operation
  input_sources: the provenance chain for all inputs
}
```

The Step is the unit of evaluation. Natural language phrasing and tool call syntax are both resolved to Steps before enforcement. Rephrasing does not change the Step. Paraphrasing does not change the Step. Only the underlying action, target, and provenance matter.

This is why prompt injection and jailbreaks that operate at the language level cannot affect enforcement outcomes — the enforcement boundary operates below the language level.

---

## Taint and Provenance

Provenance tracks where the inputs to a Step originated.

Taint is a property of inputs that have passed through untrusted or uncontrolled channels. Taint propagates forward through the `input_sources` chain — if a tainted value feeds into a later action, that action is tainted.

A tainted Step cannot trigger external side effects, even if the action itself is present in the manifest. This produces `DENY_POLICY`.

This captures a class of attacks that capability-removal alone does not address: attacks that use only legitimate actions, chained through untrusted data. The zombie scenario is the canonical example:

```
file_read (untrusted doc)    →  ALLOW
summarize                    →  ALLOW
send_email (external)        →  DENY  [POLICY: tainted source]
```

Each action is individually legal. The chain is not. Taint propagation enforces this without requiring the system to understand the attacker's intent.

**Taint is monotonic** — a derived value inherits the least-trusted provenance class among its parents. Wrapping an untrusted value in a derived wrapper does not launder it.

---

## ABSENT vs POLICY

Two denial types with distinct meanings:

**DENY_ABSENT** — The action has no representation in this world manifest. It cannot be invoked because it does not exist. This is ontological removal. No evaluation occurs; there is nothing to evaluate against.

- Immune to prompt injection, jailbreaks, and rephrasing — the capability simply does not exist
- Not a block — an absence

**DENY_POLICY** — The action exists in the manifest, but this specific call violates the provenance or parameter constraints. This is contextual enforcement within the defined world.

- Applies within the manifest boundary — legitimate capabilities constrained by context and origin
- The tool exists; this invocation does not satisfy its declared constraints

Both denials are deterministic. Neither involves judgment, probability, or LLM reasoning.

The distinction matters operationally:

| Type | Structural meaning | Can be circumvented by rephrasing? |
|---|---|---|
| `ABSENT` | The action does not exist in this execution environment | No — there is no object to reach |
| `POLICY` | The action exists, but this specific call violates its constraints | No — enforcement is deterministic against the compiled manifest |

### Expansion Invariant

The action set of the compiled world is sealed at compile time and cannot be expanded at runtime by any signal — including adversarially crafted inputs.

A prompt injection that attempts to introduce a new capability, invoke an unlisted tool, or redefine the scope of an existing action produces `DENY_ABSENT`. There is no object to reach. The attempt does not trigger a policy evaluation — it fails structurally before evaluation begins.

This invariant holds because the runtime consumes the Compiled World, not the raw manifest. No runtime signal reaches the compiler. The world is defined once, before the agent runs.

---

## Safe Compression

The invariant applied by the compiler when deriving a capability profile from execution traces:

> You can lose precision, but you cannot add capabilities.

Only `safe=True` calls contribute to the capability profile. No tool, no path, no domain that was not observed in a safe call can appear in the resulting manifest.

A manifest derived from observed execution is evidence-backed, not guessed. A hand-written manifest is an assumption about what a workflow needs; a derived manifest is grounded in what the workflow actually did.

---

## Design-Time vs Runtime Control

The world manifest is compiled before the agent runs. This is load-bearing.

**Why design-time enforcement is not a convenience — it is an architectural requirement:**

Runtime LLM-based enforcement is a stochastic system attempting to constrain another stochastic system. Both share failure modes. Both can be confused by adversarially crafted inputs. A stochastic system cannot reliably constrain another stochastic system with the same failure modes.

Design-time enforcement avoids this entirely. The manifest is not a soft constraint. It is the complete description of what can exist during execution. Enforcement is a lookup, not a judgment.

Shifting capability definition from runtime decisions to design-time boundary definition:
- reduces operational complexity (O(n) runtime review → O(1) design-time definition)
- eliminates the class of failure where the enforcement system and the enforced system share failure modes
- makes the security posture auditable, reproducible, and testable
