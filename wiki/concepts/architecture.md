# The Four-Layer Architecture

**Source:** `WHITEPAPER.md`

Agent Hypervisor operates through a four-layer architecture designed to provide ontological security. Rather than asking "Is this action forbidden at runtime?", the architecture asks "Does this action exist in the agent's universe?"

## The Layers

### Layer 0: Execution Physics
*Infrastructure Isolation*
This layer handles standard infrastructure constraints: sandboxes, containers, network and filesystem isolation. It makes certain actions physically impossible at the infrastructure level. This forms the absolute bedrock, but does not rely on agent-specific semantics.

### Layer 1: Base Ontology
*Design-Time Vocabulary*
Defines the vocabulary of actions the agent may *ever* propose. This is where tools are specialized into capabilities, parameter validation is set, and schemas are enforced. If an action is not defined in the Base Ontology, it simply does not exist—the agent cannot formulate intent for it.

### Layer 2: Dynamic Ontology Projection
*Runtime Context*
Projects the Base Ontology into a context-dependent subset currently visible to the actor. It governs the construction of [Semantic Events](manifest-resolution.md), assigns classification and taint, and determines what capabilities the actor has right now based on role, task, environment, and specific triggers.

### Layer 3: Execution Governance Gateway
*Deterministic Evaluation*
This is the runtime engine. It evaluates [Proposed Actions](manifest-resolution.md) deterministically—without an LLM. It manages provenance chains, policy rules, and taint checks to yield decisions: `allow`, `deny`, `ask` (require approval), or `simulate`.

## Philosophy
This architecture mirrors classical hypervisors:
- Virtualizing meaning, actions, and consequences instead of CPU/RAM/IO.
- Just as a Guest OS is isolated by MMU, the Agent is confined by policies that make dangerous actions structurally nonexistent.
