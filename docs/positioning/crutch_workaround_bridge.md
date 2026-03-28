# Crutch / Workaround / Bridge

*A classification framework for AI security approaches.*

---

## Core Question

Does this system:

- **block attacks?**
- or **redefine the agent's world?**

These are not the same thing. A system that blocks attacks operates inside an
unsafe architecture and tries to intercept what escapes it. A system that
redefines the world changes what can be expressed at all.

The distinction determines whether safety is probabilistic or structural,
bypassable or architectural, bounded or unbounded in cost as attacks evolve.

---

## Definitions

### 🔴 Crutch

A system that treats symptoms rather than cause.

- Probabilistic — works most of the time, not all of the time
- Bypassable — adaptive attacks circumvent it by design
- Post-perception — operates after unsafe inputs have already entered the pipeline
- Does not change the underlying architecture
- Maintenance cost scales with attack sophistication

The failure mode: a new attack variant bypasses it. The fix is a new rule.
This is a permanent treadmill.

**Examples:**
- Regex and keyword filters
- Prompt injection classifiers
- Basic LLM-as-judge safety checks
- Output content scanners

---

### 🟡 Workaround

A system that solves an immediate problem without fixing the root cause.

- Solves specific attack classes at the point of application
- Partial protection — bounded scope, uncovered flanks
- Production-usable — real reduction in risk
- Still operates inside an architecturally unsafe pipeline
- Coverage degrades as agent capabilities expand

The failure mode: the system's guarantees end exactly where its explicit rules
end. What it does not enumerate, it does not cover.

**Examples:**
- LangChain security layers and callbacks
- Runtime monitoring and anomaly detection
- Tool allow/deny lists
- LLM firewalls with structured rule sets

---

### 🟢 Bridge

A system that introduces the correct architectural direction.

- Changes what can exist, not what is permitted
- Structural — guarantees hold by construction, not configuration
- Composable — works with and strengthens other approaches
- Reduces attack surface before the agent encounters it
- Cost does not scale with attack sophistication

The failure mode is bounded and explicit: you can state exactly what it does
not cover (the semantic gap). What it covers, it covers completely.

**Examples:**
- Capability-based security systems
- Partial sandboxing with explicit ontological structure
- Early ontology-based approaches to action scoping

---

## The Key Distinction

**Crutch and Workaround ask:**

> "Can we stop this attack?"

**Bridge asks:**

> "Can this action exist in this world?"

The first question is reactive. It assumes the attack is expressible and
tries to detect it after the fact. The second question is generative. It
defines a world where the attack cannot be expressed.

This is not a performance optimization. It is a different problem class.

---

## The Permission Security Trap

Most AI security operates in permission security mode:

```
Agent → proposes action → policy checks → allow or deny
```

The agent can express any action. The policy tries to catch dangerous ones.
Two structural problems follow:

1. **The policy must anticipate every dangerous action.** Attackers need to
   find one that it missed. Asymmetric cost.

2. **The policy operates on the output of an LLM.** The LLM was persuaded to
   produce a dangerous action expression. The policy is downstream of the
   compromise.

Ontological security changes the order:

```
Design-time: define what actions exist
Runtime:     agent can only propose actions that exist
             policy evaluates within that bounded space
```

Dangerous actions that were never defined cannot be proposed, cannot be
expressed, cannot be evaluated. They are not denied — they are absent.

---

## Mapping to Agent Hypervisor

Agent Hypervisor is:

→ NOT a Crutch — it does not filter outputs or classify prompts
→ NOT a Workaround — it does not add rules to an unsafe pipeline
→ A Bridge toward: **Ontological Security**

Where:
- actions are **constructed**, not filtered
- capabilities are **rendered**, not granted
- unsafe actions are **impossible**, not denied

The World Manifest defines the boundary of existence for the agent. What is
not in the manifest does not exist in the agent's world. An agent with
`send_report_to_security(body)` cannot exfiltrate to an arbitrary recipient
— not because a rule blocks it, but because `send_email(to, body)` does not
exist in its world.

---

## Connection to World Manifest

The Crutch / Workaround / Bridge taxonomy maps directly to where in the
pipeline a security mechanism applies:

```
Input arrives
      │
      ▼
[🔴 Crutch]      Stage 2 — canonicalization, filtering, sanitization
      │           Operates after perception. Input has already entered.
      │           Unsafe content is in the pipeline. Race to catch it.
      ▼
Agent processes
      │
      ▼
[🟡 Workaround]  Stage 5 — policy enforcement, execution gate
      │           Intercepts at the execution boundary.
      │           Dangerous action was expressed; trying to catch it here.
      ▼
Execution happens (or is blocked)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[🟢 Bridge]      Stage 0 — design-time world compilation
                  Operates before the agent exists.
                  The World Manifest defines what can exist.
                  Dangerous actions are not blocked. They are absent.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Crutch** → operates after perception, downstream of the compromise point
**Workaround** → operates at the execution boundary, after dangerous intent formed
**Bridge** → operates at design time, before the agent's world is instantiated

The World Manifest is the boundary of existence. The compiler produces a
closed action space. The runtime enforces within that space. Security is not
achieved by better filtering — it is achieved by defining a smaller world.

This aligns with the Minimal Viable Semantic (MVS) model: the world manifest
encodes only what the agent legitimately needs. Everything else does not exist.

---

## Why Workarounds Don't Scale

A Workaround's coverage is proportional to its enumeration of threats.

As agents become more capable:
- The action space expands
- The output space expands
- The combinatorial explosion of possible dangerous actions grows

A Workaround that covers today's threat model has fixed coverage against an
expanding attack surface. The gap grows. New capabilities require new rules.
The system cannot keep up because it is reacting to a moving target.

A Bridge's coverage is proportional to the World Manifest's definition of
the agent's world. As the manifest grows, so does coverage — linearly. Adding
a new capability to the manifest simultaneously adds it to the governed space.
The system is not reacting; it is defining.

---

## Honest Limitations

Agent Hypervisor is a Bridge, not a complete solution.

A Bridge introduces structural correctness. It does not solve:
- **The semantic gap** — the manifest must be correct. If the manifest
  permits a dangerous action, the system permits it too.
- **Manifest authoring** — the quality of security depends on the quality
  of the manifest. Bad manifest = bad security.
- **LLM reasoning errors** — an LLM operating inside a correctly defined
  world can still make bad inferences within that world.

A Bridge is not the end of security. It is the correct foundation for
building the rest.
