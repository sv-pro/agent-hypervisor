# FAQ — Agent Hypervisor

*Answers to conceptual questions before you read the whitepaper.*

---

## "Isn't this just a guardrail?"

No. A guardrail sits beside the agent and tries to detect bad behavior after it occurs. Guardrails operate at the same level as the threat: they are probabilistic, bypassable under sufficient adversarial pressure, and invisible to the system they protect.

Agent Hypervisor is not a guardrail. It is a **virtualization layer**. The agent does not operate in raw reality and then get filtered — the agent operates inside a constructed world where dangerous actions do not exist. There is nothing to guard against because the threat surface is never exposed.

The distinction is ontological, not behavioral. A guardrail says "you are not allowed to do X." The hypervisor says "X does not exist in this world."

---

## "Isn't this just a policy engine?"

Partially, but the framing misses what matters. Policy engines evaluate requests against rules. That evaluation can be bypassed if the input is ambiguous, the rule is incomplete, or the engine itself is probabilistic.

The World Policy (Layer 4) is deterministic: same input, same output, always. It is unit-testable without mocking. But what makes Agent Hypervisor more than a policy engine is the **virtualization** that precedes it. Raw input never reaches the agent to generate a policy-worthy request. The agent sees only Semantic Events — structured, attributed, taint-tracked objects. The policy engine operates on a cleaned, typed representation, not on raw text.

A policy engine is one component of the architecture. The architecture is the thing that prevents malformed inputs from ever reaching the point where a policy decision is needed.

---

## "Isn't this just a sandbox?"

A sandbox isolates a process from the host system — it restricts what the process can *do*. Agent Hypervisor also restricts what the agent can *perceive*. That is the difference.

In a sandbox, the agent receives raw input (emails, web content, tool outputs) and has limited ability to act on it. The agent can still be manipulated by that input — prompt injection, memory poisoning, and tainted reasoning all happen inside the sandbox.

Agent Hypervisor virtualizes the input itself. The agent never sees raw email text; it sees a `SemanticEvent` with `trust_level: UNTRUSTED` and `taint: true`. The agent cannot be confused about what it is looking at, because what it is looking at is structurally different from instructions.

Sandbox: restricts output capability. Hypervisor: also restricts input reality.

---

## "Isn't this just an MCP proxy?"

No. An MCP proxy sits between the agent and MCP servers to filter tool calls. That is Layer 5 (Execution Boundary) behavior — intercepting outputs before they reach external systems.

Agent Hypervisor intercepts at both ends: input (Layer 1) and output (Layer 5). The MCP Gateway is one planned component of Layer 5. But the security properties that matter most happen at Layer 1 (before the agent sees anything) and Layer 4 (before any effect reaches reality). An MCP proxy without those layers is a single-point filter that does not address prompt injection, memory poisoning, or taint propagation.

The hypervisor is the full five-layer stack. An MCP proxy is a future module within that stack.

---

## "The semantic gap means Layer 1 needs intelligence. Doesn't that reintroduce probabilistic components?"

Yes. This is a real tension, acknowledged explicitly in [CONCEPT.md §Honest Weaknesses](CONCEPT.md).

The hypervisor's response is structural containment rather than elimination. Intelligence is required at Layer 1 to classify trust, strip injection patterns, and extract structured Semantic Events from unstructured input. If that intelligence is an LLM, probabilistic behavior re-enters at the boundary.

The architecture handles this in two ways:

1. **Isolation.** Layer 1 failure does not cascade. If a Semantic Event is incorrectly classified, Layers 2–5 remain fully deterministic. The damage is bounded to what a miscategorized event can cause at its assigned trust level.
2. **Tunable conservatism.** A stricter policy at Layer 1 (narrower input acceptance) reduces the attack surface proportionally. The semantic gap is real but it is bounded, explicit, and tunable — unlike a runtime LLM guardrail whose failure modes are open-ended.

The correct framing: Agent Hypervisor does not eliminate the need for intelligence at the boundary. It isolates that intelligence to one layer, makes its failure modes bounded, and ensures that deterministic properties hold everywhere else.

---

## "Why move HITL to design-time instead of keeping it at runtime?"

Runtime HITL (prompting a human for approval on each action) does not scale. An agent processing hundreds of tool calls per session cannot pause for human review on each one. In practice, humans rubber-stamp prompts they do not fully understand, approval fatigue sets in, and the HITL gate becomes theater.

Design-time HITL amortizes human judgment across many interactions. A human reviews and commits the World Manifest — which defines what tools exist, which trust levels apply, which actions are irreversible, and what the budget limits are. That review happens once (or on manifest updates). Every runtime session executes deterministically within that reviewed boundary.

This is the "AI Aikido" principle: LLM capability is used at design-time to generate sound deterministic artifacts. The intelligence designs the physics; it does not govern individual actions at runtime.

The tradeoff is explicit: design-time HITL cannot handle situations not anticipated in the manifest. Novel attack patterns require manifest redesign. This is an engineering problem with a finite improvement path, not an unbounded probabilistic failure mode.

---

## "What does the architecture actually guarantee? What remains unsolved?"

**What is guaranteed (for every physics law in the World Policy):**

- The same Intent Proposal always produces the same decision.
- A tainted object cannot reach Layer 5 without an explicit sanitization gate.
- A tool not in the World Manifest cannot be invoked — the agent cannot form the intent.
- Budget exhaustion results in hard termination, not soft degradation.
- Every effect on external reality passes through an immutable audit log.

These properties are binary, unit-testable, and reproducible without mocking the agent.

**What remains unsolved:**

- Semantically ambiguous injections that pass the Layer 1 classifier undetected (the semantic gap).
- World Manifest design errors — a poorly designed manifest produces a poorly secured world. The runtime is correct; the specification may not be.
- Novel attack patterns not anticipated at design time — these require manifest iteration.
- The boundary between "deterministic classifier" and "LLM-assisted classifier" at Layer 1 is not yet formally specified.

The architecture does not claim perfect security. It claims that the failure modes are **known**, **bounded**, and **addressable through engineering** — not probabilistic drift with unknown bypass rates.

---

## "How does this relate to existing agent frameworks?"

Existing frameworks (LangChain, AutoGen, CrewAI, etc.) operate in raw reality. Agents receive unmediated input, have direct tool access, and rely on LLM-based safety layers for guardrailing. Those layers are bypassable.

Agent Hypervisor is not a framework. It is an **architectural layer** that sits between any agent and the outside world. A conformant implementation wraps an existing agent: the agent receives Semantic Events instead of raw input, and its tool calls are Intent Proposals evaluated by the World Policy.

In principle, any LLM-based agent can operate inside an Agent Hypervisor without modification to the agent itself — the agent's interface is virtualized. In practice, the integration surface (especially for MCP-based tools) is not yet implemented. See [ARCHITECTURE.md §4](docs/ARCHITECTURE.md) for current status.

---

*See [CONCEPT.md](CONCEPT.md) for the architectural overview.*
*See [WHITEPAPER.md](docs/WHITEPAPER.md) for the full thesis.*
*See [THREAT_MODEL.md](THREAT_MODEL.md) for trust channels and in-scope threats.*
*See [docs/GLOSSARY.md](docs/GLOSSARY.md) for term definitions.*
