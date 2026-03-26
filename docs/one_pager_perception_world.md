# The Perception-Bounded World — One Pager

---

## Problem

AI agents are deployed into open environments with access to powerful tools. Current safety approaches — guardrails, output filters, LLM-based supervisors — attempt to constrain behavior probabilistically.

This fails for three reasons:

1. **Probabilistic safety is delayed failure.** A 99.9% success rate at scale means daily failures. Rare errors are expensive errors.
2. **LLM-supervising-LLM is correlated failure.** Same architecture, same training, same failure modes. Redundancy without independence is not safety.
3. **Agents have no internal constraints.** No fear, no empathy, no persistent moral reasoning. All constraints must be externalized into system design.

The root cause: these approaches assume an open world and try to filter behavior after the agent has already perceived everything.

---

## Reframing

The agent does not operate in the real world. It operates in its field of perception.

The agent's world is not the Universe. It is:
- What it can perceive (input channels)
- What it can do (available actions)
- What it can remember (accessible memory)
- What it can express (representable abstractions)

If something is not perceivable, it does not exist. If something is not actionable, it cannot happen. This is not a limitation — it is the design lever.

> The question is not "what should the agent be allowed to do?"
> The question is "what should exist in the agent's world?"

---

## Solution

Design the world, not the behavior.

The Agent Hypervisor defines a closed, bounded world for each agent through a World Manifest — a formal specification of everything that exists. Raw tools are transformed into role-specific capabilities at design time. Actions outside the manifest are not blocked — they are structurally absent.

The four-layer architecture implements progressive perception bounding:

- **Layer 0** — Physical impossibility (container, network, filesystem isolation)
- **Layer 1** — Ontological boundary (what actions exist — capability rendering)
- **Layer 2** — Dynamic projection (what exists *now* — role, task, state)
- **Layer 3** — Deterministic governance (what may execute — policy, taint, budget)

Each layer shrinks the world before the next layer sees it. No LLM participates in enforcement. Same inputs always produce the same decision.

---

## Key Principles

**Safety by removal, not by filtering.**
Dangerous actions are removed from the world definition. There is nothing to bypass because there is nothing to attempt.

**Deterministic over probabilistic.**
World policy evaluation is fully deterministic and unit-testable. No stochastic component in the enforcement path.

**External constraints only.**
AI agents have no internal regulators. All safety properties must be structural properties of the system, not behavioral properties of the model.

**Ontology fit.**
The agent is not a universal actor — it is a role-bound entity. Its capabilities must match its role exactly. Surplus capability is surplus risk.

**World design is the control plane.**
Defining what exists in the agent's world is more powerful than defining what is permitted. Existence precedes permission.

---

*For the full concept: [docs/concepts/perception_bounded_world.md](concepts/perception_bounded_world.md)*
*For the architecture: [docs/ARCHITECTURE.md](ARCHITECTURE.md)*
*For the threat model: [THREAT_MODEL.md](../THREAT_MODEL.md)*
