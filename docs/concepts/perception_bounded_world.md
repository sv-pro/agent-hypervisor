# Perception-Bounded World

**The foundational reframing: agents do not operate in the real world. They operate in their field of perception.**

---

## 1. The Core Insight

Every AI agent has a world. That world is not the Universe.

The agent's world is:

- Its input channels
- Its available tools
- Its accessible memory
- Its representable abstractions

Nothing else exists. Not philosophically — structurally. If the agent cannot perceive it, it is not real to the agent. If the agent cannot act on it, it cannot happen.

This is not a limitation to work around. It is the fundamental design lever.

> The question is not "what should the agent be allowed to do?"
> The question is "what should exist in the agent's world?"

---

## 2. From Guardrails to World Design

The dominant approach to AI agent safety is guardrails: filters, classifiers, output monitors. All guardrails share a structural assumption — the agent operates in an open world, and dangerous behavior must be intercepted.

This assumption is wrong. It produces systems that are reactive, probabilistic, and perpetually incomplete.

| Property | Guardrails | World Design |
|---|---|---|
| World model | Open — agent sees everything, filters block selectively | Closed — only defined elements exist |
| Failure mode | Probabilistic — some attacks pass | Deterministic — undefined actions are structurally absent |
| Timing | Reactive — detect and block after the agent acts | Proactive — dangerous actions removed before the agent runs |
| Coverage | Asymptotic — approaches safety, never reaches it | Constructive — safety is the default state |
| Improvement | Add more rules, more classifiers, more monitors | Refine the world definition |

> Safety is achieved by removing possibilities, not reducing their probability.

A guardrail says "you are not allowed to call `send_email` with an untrusted recipient." The agent still perceives `send_email`. It still reasons about recipients. It still generates the intent. The guardrail hopes to catch it.

A perception-bounded world says: `send_email` does not exist. There is `send_report_to_security(body)`. The concept of "arbitrary recipient" is not suppressible — it is non-representable. There is nothing to catch because there is nothing to attempt.

---

## 3. Why Probabilistic Safety Fails

### 3.1 The Delayed Failure Problem

Increasing the probability of correct behavior is not safety. It is delayed failure.

A system that behaves correctly 99.9% of the time will fail. The failure will come later, when the system has earned trust, when the blast radius is larger, and when the remediation cost is highest.

> Rare errors are expensive errors.

A 0.1% failure rate on 1,000 daily agent actions means one failure per day. At 10,000 actions, one failure every 2.4 hours. Scale does not dilute the rate — it concentrates the impact.

Probabilistic safety creates a false sense of security precisely when it matters most: at scale.

### 3.2 Zombies Supervising Zombies

A common mitigation pattern: use one LLM to supervise another. A "safety model" reviews the outputs of the "working model."

This is correlated failure.

Both models share the same architecture, the same training methodology, the same class of failure modes. An adversarial input that bypasses one LLM is statistically likely to bypass another LLM of the same family. The supervisor is not independent — it is a correlated copy.

> A stochastic system cannot reliably constrain another stochastic system with the same failure modes.

This is not defense in depth. Defense in depth requires independent failure modes. Two LLMs from the same family are not independent. They are redundant — and redundancy without independence is an illusion of safety.

The correct architecture places a deterministic system — one with different failure modes — between the agent and the world.

### 3.3 Probabilistic Control Is Not Control

Control requires a guarantee: given input X, behavior Y will not occur.

Probabilistic systems offer: given input X, behavior Y is unlikely.

These are fundamentally different properties. The first is a contract. The second is a hope. You cannot build reliable systems on hopes. You cannot audit hopes. You cannot certify hopes.

The Agent Hypervisor replaces probabilistic control with deterministic world design. The guarantee is structural: if an action is not defined in the World Manifest, it cannot be proposed, evaluated, or executed. Not unlikely — impossible.

---

## 4. Internal vs. External Constraints

Humans are constrained by internal regulators: fear, empathy, social consequence, moral reasoning. These internal constraints reduce the need for external enforcement. A person does not need a physical barrier to avoid most harmful actions — internal regulation suffices for the vast majority of scenarios.

AI agents have none of these.

An LLM has no fear. No empathy. No felt consequence for harm. No persistent moral framework that resists adversarial pressure. It has statistical patterns that approximate cooperative behavior in the training distribution — and degrade unpredictably outside of it.

> All constraints on AI agents must be externalized into system design.

You cannot train an agent to be safe in the way you can raise a child to be careful. Training produces tendencies. Architecture produces boundaries. Tendencies can be overridden. Boundaries cannot be crossed — they define what exists.

The perception-bounded world is the externalization of all constraints. Instead of hoping the agent will choose correctly, you define a world where incorrect choices do not exist.

---

## 5. Ontology Fit: Roles and Creatures

An agent is not a universal actor. It is a role-bound entity.

The mistake in most agentic architectures is treating the agent as a general-purpose intelligence dropped into an environment. This produces a mismatch between the agent's capabilities and its operational boundaries — a mismatch that guarantees instability.

The correct model: the agent is a creature designed for a specific world. Its ontology — the categories, actions, and abstractions it can work with — must fit the world it inhabits.

Wrong ontology produces wrong behavior. An agent given `send_email(to, body)` when its role is "security report generator" has the wrong ontology. The existence of an unconstrained `to` parameter is an ontological error — it creates a capability space larger than the role requires.

Right ontology eliminates the gap. `send_report_to_security(body)` matches the role exactly. There is no surplus capability. No gap between what the agent can do and what it should do.

> Intelligence without ontology is instability.
> The agent must belong to the world it operates in.

A capable model placed in an unbounded world is not powerful — it is dangerous. A capable model placed in a well-defined world is not limited — it is focused.

---

## 6. The Perception Model

Formally, an agent's world W is defined by:

```
W = (P, A, M, R)

where:
  P = perception set     — the set of all inputs the agent can receive
  A = action set         — the set of all actions the agent can propose
  M = memory set         — the set of all stored state the agent can access
  R = representation set — the set of all abstractions the agent can use
```

Each component is finite and explicitly defined in the World Manifest.

**Closure property:** The agent's behavior is fully determined by W. If something is not in P, the agent cannot know about it. If something is not in A, the agent cannot attempt it. If something is not in M, the agent cannot remember it. If something is not in R, the agent cannot reason about it.

**Design implication:** Securing the agent reduces to designing W correctly. Every security property is a property of the world definition, not a property of the agent's behavior within the world.

This inverts the security problem. Instead of analyzing an unbounded space of possible agent behaviors and trying to filter out dangerous ones, you design a bounded world and prove that it contains only safe possibilities.

---

## 7. Capability Rendering

The mechanism that implements perception-bounded worlds is capability rendering: raw tools are transformed into role-specific capabilities at design time.

```
Raw tool space (unbounded):
  send_email(to, subject, body, cc, bcc, attachments)
  read_file(path)
  http_request(method, url, headers, body)
  execute_shell(command)

        ↓  capability rendering (design-time)

Rendered world (bounded):
  send_daily_report(body)          ← recipient: fixed, subject: fixed
  read_config(key)                 ← path: scoped to /config/
  fetch_weather(city)              ← method: GET, url: template, no custom headers
```

`execute_shell` does not exist. Not blocked — absent. `http_request` does not exist. Not filtered — non-representable.

The agent operates in the rendered world. The rendered world is the only world that exists.

---

## 8. Connection to the Agent Hypervisor Architecture

The perception-bounded world model is the theoretical foundation for the four-layer architecture:

| Layer | Role in perception bounding |
|---|---|
| Layer 0: Execution Physics | Physical impossibility — network, filesystem, container isolation |
| Layer 1: Base Ontology | Defines what exists — capability rendering from raw tool space |
| Layer 2: Dynamic Ontology Projection | Defines what exists *now* — role, task, and state narrow the world further |
| Layer 3: Execution Governance | Deterministic evaluation of what may execute within the bounded world |

Each layer shrinks the perception boundary. By the time the agent operates, its world contains only what was designed to be there.

The World Manifest is the formal specification of the perception boundary. The compiler transforms it into deterministic runtime artifacts. The hypervisor enforces it.

> The agent does not see the universe. It sees the world you built for it.
> Build the right world, and behavior follows.

---

*See [ARCHITECTURE.md](../ARCHITECTURE.md) for the implementation-level view.*
*See [GLOSSARY.md](../GLOSSARY.md) for term definitions.*
*See [../THREAT_MODEL.md](../../THREAT_MODEL.md) for threat analysis through this lens.*
