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

A minimal example:

```yaml
workflow_id: repo-maintenance
version: "1.0"

capabilities:
  - tool: file_read
    constraints:
      paths: ["**/*.py", "**/*.md"]
  - tool: shell_exec
    constraints:
      commands: ["pytest"]
  - tool: git_push
    constraints:
      remotes: [origin]
```

`http_post`, `env_read`, and unrestricted `shell_exec` are not in the manifest — they do not exist in this agent's world.

What the manifest is not:

- a runtime filter
- a permission system checked at invocation time
- a behavioral heuristic evaluated probabilistically

The manifest is a structural definition. Capabilities outside it have no representation. Enforcement against the manifest is deterministic. **The manifest is the world** — the agent operates inside it, not alongside it.

---

## Compiler

The compiler implements Layer 1 of the architecture. It takes a workflow definition or observed execution trace, derives the minimal capability set required, and produces the World Manifest.

```
Workflow definition / execution trace
      ↓
 [profile]   derive minimal capability set
      ↓
 World Manifest (YAML)
      ↓
 [render]    Manifest → Rendered Capability Surface
      ↓
 [enforce]   ALLOW / DENY_ABSENT / DENY_POLICY
```

The compiler is a pure transformation — no LLM calls, no runtime decisions, no mutable state. The output is a sealed artifact that cannot be expanded during execution.

**Derivation vs declaration.** A manifest can be authored by hand or derived from execution traces. A derived manifest is evidence-backed: only capabilities observed in `safe=True` calls contribute to the profile. A hand-written manifest is an assertion about what a workflow needs; a derived manifest is a record of what it actually used.

**CLI.** The `awc` (Agent World Compiler) tool drives the pipeline:

```bash
awc profile --trace path/to/trace.json    # derive capability set from observed trace
awc compile --manifest manifest.yaml      # compile into sealed policy artifacts
awc render  --manifest manifest.yaml      # inspect the rendered capability surface
awc run     --scenario safe               # run a named end-to-end scenario
```

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

Provenance is the record of where a value came from and how it was transformed before it reached the tool execution boundary. It is a first-class property of every value in the system — not metadata attached as an afterthought.

**Provenance classes.** Values are classified by trust level at their origin:

| Class | Meaning | Trust |
| --- | --- | --- |
| `external_document` | Content from files, emails, web pages, API responses | Lowest |
| `derived` | Computed or extracted from one or more parent values | — |
| `user_declared` | Explicitly declared by the operator in the task manifest | High |
| `system` | Hardcoded by the system — no user influence possible | Highest |

**Taint** is the observable consequence of provenance: a value that traces to `external_document` ancestry is tainted. Taint propagates forward through the derivation chain — if a tainted value feeds into a later action, that action is tainted.

A tainted Step cannot trigger external side effects, even if the action itself is present in the manifest. This produces `DENY_POLICY`.

This captures a class of attacks that capability-removal alone does not address: attacks that use only legitimate actions, chained through untrusted data. The zombie scenario is the canonical example:

```
file_read (untrusted doc)    →  ALLOW
summarize                    →  ALLOW
send_email (external)        →  DENY  [POLICY: tainted source]
```

Each action is individually legal. The chain is not. Taint propagation enforces this without requiring the system to understand the attacker's intent.

**Provenance DAG.** When a value is derived from other values, the derivation is recorded — forming a directed acyclic graph of origins. The firewall walks this graph at evaluation time to compute effective trust. The full chain is always evaluated; provenance claims on the leaf node alone are not sufficient.

**Sticky provenance (anti-laundering invariant).** A derived value inherits the least-trusted provenance class among all its ancestors. Wrapping an untrusted value in a derived wrapper does not launder it:

```
attacker embeds address in document
    doc_ref  (external_document)
         │
         ▼
agent extracts address
    addr  (derived — parent: doc_ref)

operator declares contacts file
    contacts_ref  (user_declared)
         │
         ▼
combined address  (derived — parents: addr + contacts_ref)
    ← external_document present in ancestry
    ← least-trusted dominates → deny
```

Even though `contacts_ref` is trusted, the `external_document` ancestor in the chain dominates. The combination does not produce a trusted value.

**Taint is monotonic** — it can be joined but never removed. Any code that drops or bypasses taint propagation is a security regression.

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

---

## Runtime Enforcement

The runtime is Layer 3 of the architecture — the deterministic enforcement kernel.

The enforcement boundary is `IRBuilder.build()`. All constraint checking happens at construction time — before any execution begins. If `build()` returns an `IntentIR`, every constraint has already passed and the sealed intent is handed to the executor. If it raises, nothing executes.

```text
Agent / LLM
    │
    ▼
IRBuilder.build()       ← all enforcement happens here
    │ success → IntentIR (sealed)
    ▼
Executor.execute()      ← runs only validated intent
    │
    ▼
TaintedValue            ← result always carries provenance
```

Four structurally distinct denial types, all subclasses of `ConstructionError`:

| Exception | Meaning |
| --- | --- |
| `NonExistentAction` | Tool not in manifest — ontological absence |
| `ConstraintViolation` | Trust level insufficient for this action |
| `TaintViolation` | Tainted context cannot flow into this action |
| `ApprovalRequired` | Action requires an explicit approval token |

**IntentIR is sealed.** The `IntentIR` object cannot be constructed outside `IRBuilder`. No external code can inject an execution intent that has not passed all constraints.

**Process boundary.** Handler code runs in a worker subprocess. Policy evaluation runs in the main process. Neither can see the other's internals. This is OS-level isolation — not a convention.

**SafeMCPProxy.** All MCP-style tool calls pass through `SafeMCPProxy` before reaching the execution layer. Enforcement is in-path — there is no call path that bypasses evaluation.

---

## Tool Virtualization

In the standard model, tools connect directly to agents. A compromised tool inherits the full blast radius of the agent's access. Agent Hypervisor interposes a virtualization layer:

```text
Standard model:
    Agent ←→ MCP Tool  (direct, unmediated)

Agent Hypervisor model:
    Agent ←→ Hypervisor ←→ MCP Tool  (virtualized device)
```

**MCP tool = virtualized device.** A tool exists in the agent's world only if the World Manifest defines it. An undefined tool is not forbidden — it does not exist. The agent cannot formulate intent for a tool that has no ontological representation.

**Schema = device descriptor.** Every tool has a typed schema defining accepted inputs and expected outputs, validated at compilation time. Malformed or unexpected payloads are rejected deterministically before any execution.

**Capability = permission model.** The capability matrix determines which tools are available at which trust levels. If the trust level does not grant the required capability, the call does not execute — not because a filter caught it, but because the capability does not exist in that trust context.

**Supply chain.** Skills require World Manifest entries to exist. An unvetted skill is not blocked — it is undefined. The agent operates in a world where that skill has never existed. There is no request to intercept.

This resolves a class of attacks that filtering cannot address: even if a malicious skill or server is present in the environment, the agent has no representation of it and cannot form intent for it.
