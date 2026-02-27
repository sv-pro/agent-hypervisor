# Design-Time Human-in-the-Loop: Why the Economics of Agent Security Are Wrong

*Part 3 of "The Missing Layer" — a series on architectural security for AI agents*

---

[IMAGE: 3A — "HITL Economics" — O(n) vs O(log n) curves]

[Part 1](link) showed every AI defense breaks under adaptive attacks. [Part 2](link) showed how AI Aikido resolves the boundary paradox by separating design-time intelligence from runtime enforcement.

But where does the human fit?

Every industry response to agent security invokes "human-in-the-loop." Require human approval for high-risk actions. Review behavior. Audit logs. The recommendation appears in every article, every vendor pitch, every framework.

The problem: the economics of runtime human-in-the-loop don't work. And the industry knows it.

---

## The Economics Are Broken

The average enterprise SOC receives 10,000 alerts per day. Each requires 20–40 minutes to investigate. Even fully staffed teams handle only 22%. More than 60% of teams have admitted to ignoring alerts that later proved critical.

CrowdStrike documents breakout times of 51 seconds. If AI agents process thousands of requests per hour, each requiring potential human review, the math collapses.

Bruce Schneier describes a "security trilemma": enterprises can optimize for speed, intelligence, or security — but not all three. Anthropic's data illustrates it directly. Their strongest attack resistance is in constrained environments. Their weakest is in autonomous ones. The more useful the agent, the less secure it becomes under runtime oversight.

Gartner predicts over 40% of agentic AI projects will be canceled by end of 2027 — not from technical failure, but inadequate governance. The projects work. Organizations can't figure out how to supervise them at scale.

Runtime human-in-the-loop is O(n) — each decision costs the same human attention. One agent, manageable. A hundred agents processing thousands of requests, impossible.

---

## Amortize, Don't Spend

SOC teams implementing "bounded autonomy" define upfront which alert categories agents handle autonomously, which require human review, and which escalation paths apply below confidence thresholds. One design-time decision amortizes across every future alert in that category.

This isn't new. It's how constitutions work. Expensive to draft, but the cost amortizes across every citizen and every moment of governance. No one reviews every transaction against the full text of the law in real-time.

**Runtime HITL: Cost = O(n)** per decision. Every request potentially needs attention.

**Design-Time HITL: Cost = O(log n)** per iteration covering n decisions. Each iteration covers exponentially more cases.

---

## Three Modes, Not One

[IMAGE: 3B — "Four-Phase Cycle" diagram]

The industry treats "human-in-the-loop" as one concept. It's three:

**Design-Time Human (scales).** Reviews and approves World Manifests, taint rules, capability matrices, escalation thresholds. One decision covers thousands of runtime cases. Like writing a constitution.

**Runtime Human — exception, not rule.** The `require_approval` decision is a pressure relief valve for cases design-time didn't cover. Critical signal: if it fires frequently, the World Manifest is underdefined. That's not failure — it's feedback triggering design-time iteration.

**Iteration-Time Human (feedback loop).** Runtime logs reveal patterns: "47 escalations this week on rule X." "Zero bypasses on parser set Z." The human analyzes. The LLM generates updated rules. Tests run. Escalations drop. The system learns — through deterministic artifacts, not stochastic adaptation.

VMware engineers didn't sit beside every VM. They designed isolation rules once. VMs scaled without human intervention. The same model applies.

---

## The Evidence Is Here

**SOC bounded autonomy** achieves 98%+ agreement with human decisions while cutting 40+ hours weekly. The design-time boundary — which categories are autonomous — does the heavy lifting.

**OpenClaw's 48-hour weaponization** proves runtime oversight fails at speed. The tool went from zero to 180,000 stars. Infostealers added it to target lists before security teams knew it existed. By the time a human reviewer catches the issue, thousands of instances are compromised.

**CX platform security gaps** show the business blast radius. When a CX AI engine triggers a compensation adjustment based on poisoned sentiment data, the damage isn't a security incident — it's a wrong business decision at machine speed. No runtime review catches poisoned data flowing through approved API calls.

**Opus 4.6 evades its own monitor 18% of the time** on SHADE-Arena. If the agent can reason about its own oversight, runtime monitoring has a ceiling. Design-time constraints — what the agent can access, what actions exist — don't depend on agent cooperation.

---

## The Four-Phase Cycle

**Design:** Human + LLM co-create the World Manifest. Action schemas, trust policies, taint rules. Human reviews and commits.

**Compile:** Manifest → deterministic artifacts. Policy tables, validators, taint matrices. No LLM survives. All unit-testable.

**Deploy:** Pure deterministic runtime. No LLM, no human. Reproducible and auditable.

**Learn:** Logs accumulate. Escalation patterns emerge. Coverage gaps become visible.

**Redesign:** Human reviews patterns. LLM generates updates. Adversarial testing validates. Recompile. Coverage expands.

Each cycle: deterministic coverage increases. Exception rate decreases. Human effort concentrates on novel edge cases.

---

## Why Now

Dario Amodei expects continuous learning within 1–2 years. When it arrives, memory poisoning becomes permanent corruption. The agent doesn't process one bad input — it carries contamination into every future interaction.

Today, a poorly supervised agent can be reset. Tomorrow, it can't.

The window for design-time governance — World Manifests, compilation pipelines, provenance tracking for learning gates — is months, not years. The 40% cancellation rate Gartner predicts isn't a technology failure. It's a governance architecture failure.

---

**Next:** [MCP, OpenClaw, and the Missing Virtualization Layer](link) — the final article in this series.

*Open-source PoC: [Agent Hypervisor](https://github.com/sv-pro/agent-hypervisor)*

*Personal analysis. Does not represent Radware's position.*
