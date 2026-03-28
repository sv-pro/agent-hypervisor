# AI Security Approaches — Comparison Table

*Evaluated against the Crutch / Workaround / Bridge framework.*

See [crutch_workaround_bridge.md](crutch_workaround_bridge.md) for framework definitions.

---

## Comparison

| Approach | Type | Where Applied | Determinism | Bypass Risk | Scales With Threat Growth |
|----------|------|--------------|-------------|-------------|--------------------------|
| **Regex / keyword filters** | 🔴 Crutch | Post-input, pre-LLM | Deterministic | High — trivial rephrasing | No — each variant needs a new rule |
| **Prompt injection classifiers** | 🔴 Crutch | Post-input, pre-LLM | Probabilistic | High — adversarial inputs evade classifiers | No — classifiers chase adversarial distribution |
| **LLM-as-judge safety** | 🔴 Crutch | Post-output | Probabilistic | High — judge and agent share the same failure modes | No — same LLM weaknesses apply to both |
| **Output content scanners** | 🔴 Crutch | Post-output | Mixed | Medium — post-hoc, after action is already expressed | No — coverage = enumeration of known bad patterns |
| **LangChain security layers** | 🟡 Workaround | Execution boundary | Mixed | Medium — bypassed by indirect / multi-step attacks | Partial — must be updated as capabilities expand |
| **Tool allow/deny lists** | 🟡 Workaround | Execution boundary | Deterministic | Medium — doesn't govern argument content or sequences | Partial — list maintenance grows with tool count |
| **Runtime monitoring / anomaly detection** | 🟡 Workaround | Post-execution signal | Probabilistic | Medium — monitors behavior, cannot prevent novel patterns | Partial — anomaly models drift as behavior changes |
| **LLM firewall (rule-based)** | 🟡 Workaround | Input/output boundary | Mixed | Medium — structured rules, limited expressiveness | Partial — rules must anticipate attack vocabulary |
| **Capability-based systems (partial)** | 🟢 Bridge | Design-time scoping | Deterministic | Low — attack surface reduced by construction | Yes — new capabilities enter the governed space |
| **Agent Hypervisor** | 🟢 Bridge | Design-time world compilation | Deterministic | Low (bounded by semantic gap) | Yes — manifest growth = coverage growth |

---

## Column Definitions

**Type** — Crutch / Workaround / Bridge classification per [framework](crutch_workaround_bridge.md).

**Where Applied** — point in the pipeline where enforcement occurs.
- *Post-input, pre-LLM* — after input arrives, before the agent processes it
- *Post-output* — after the agent produces output
- *Execution boundary* — between agent intent and tool execution
- *Design-time world compilation* — before the agent's world is instantiated

**Determinism** — whether the enforcement decision is deterministic given the same input.
- *Deterministic* — same input → same decision, always
- *Probabilistic* — same input → decision depends on model state / sampling
- *Mixed* — deterministic core with probabilistic components

**Bypass Risk** — structural susceptibility to adversarial evasion.
- *High* — bypass is straightforward and does not require significant attacker effort
- *Medium* — bypass requires effort; some attack classes are genuinely blocked
- *Low* — bypass requires defeating the structural property, not just the surface check

**Scales With Threat Growth** — whether the system maintains coverage as agent capabilities and attack sophistication increase.
- *No* — coverage is fixed at time of deployment; growing attack surface is not covered
- *Partial* — coverage grows with explicit updates; requires ongoing maintenance
- *Yes* — coverage grows structurally as the manifest grows; no per-attack maintenance needed

---

## Key Observations

**Determinism alone is not sufficient.**

Tool allow/deny lists are deterministic but are a Workaround: they control
which tools exist but not what arguments are passed or how sequences combine.
Determinism is necessary for auditable security; it is not the same as
structural security.

**Probabilistic components break audit chains.**

Any system with a probabilistic component in the enforcement path cannot
provide a closed audit trail. You cannot explain why a decision was made if
the decision depended on a model's hidden state. Agent Hypervisor's
enforcement path is fully deterministic from IRBuilder through execution.

**"Low bypass risk" has an explicit boundary.**

Agent Hypervisor's bypass risk is bounded by the semantic gap: if the World
Manifest incorrectly defines the agent's world, the system correctly enforces
an incorrect world. This is not "zero risk" — it is a *known, explicit, bounded*
risk that the operator can reason about and test.

---

## What This Table Does Not Cover

- **Deployment complexity** — Bridge approaches require upfront design investment.
  Crutches are faster to deploy. This is a real tradeoff, not a dismissal.
- **Layering** — these approaches are not mutually exclusive. Agent Hypervisor
  as a Bridge can be combined with Workarounds for defense in depth.
- **Semantic gap coverage** — no approach in this table eliminates the semantic
  gap fully. The gap is a property of natural language, not of the security system.
