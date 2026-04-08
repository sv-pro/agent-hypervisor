# Design-Time Human-in-the-Loop: Why the Economics of Agent Security Are Wrong

*Part 3 of "The Missing Layer" — a series on architectural security for AI agents*

*Personal analysis — does not represent Radware's position*

---

The previous articles established two things. First, every tested AI defense breaks under adaptive attacks because they all operate after the agent has perceived dangerous input. Second, AI Aikido — using LLM intelligence at design-time to generate deterministic runtime artifacts — resolves the paradox of needing intelligence at the security boundary.

But there's a question both articles left unanswered: **where does the human fit?**

Every industry response to AI agent security invokes "human-in-the-loop" as the answer. Require human approval for high-risk actions. Review agent behavior. Audit logs. The recommendation appears in every article, every vendor pitch, every security framework.

The problem is that the economics of runtime human-in-the-loop don't work. And the industry knows it.

## The Economics Are Broken

The average enterprise SOC receives 10,000 alerts per day. Each requires 20 to 40 minutes to investigate properly. Even fully staffed teams handle only 22% of them. More than 60% of security teams have admitted to ignoring alerts that later proved critical.

CrowdStrike documents breakout times of 51 seconds. Attackers move from initial access to lateral movement before most security teams get their first alert. If AI agents process thousands of requests per hour, each requiring potential human review, the math collapses immediately.

Bruce Schneier describes the problem as a "security trilemma": enterprises can optimize for speed, intelligence, or security — but not all three. Anthropic's own data illustrates the tradeoff. Their strongest attack resistance is in constrained environments (narrow, limited). Their weakest is in autonomous environments (broad, flexible). The more useful the agent, the less secure it becomes under the current model.

Gartner predicts over 40% of agentic AI projects will be canceled by the end of 2027, with unclear business value and inadequate governance as the main drivers. Not technical failure — governance failure. The projects work technically but organizations can't figure out how to supervise them at scale.

Runtime human-in-the-loop is O(n) — each decision costs the same amount of human attention. One agent, maybe. Ten agents, strained. A hundred agents processing thousands of requests, impossible.

## The Insight: Amortize, Don't Spend

There's a different model. It's already working in practice. And it has a formal economic structure.

SOC teams implementing "bounded autonomy" define upfront which alert categories agents can act on autonomously, which require human review regardless of confidence score, and which escalation paths apply when certainty falls below threshold. One design-time decision — defining the boundary — amortizes across every future alert in that category.

This is not a new idea. It's how constitutions work. A constitution is expensive to draft. But its cost is amortized across every citizen and every moment of governance. No one suggests reviewing every transaction against the full text of the law in real-time. The law is compiled into institutional structures that execute deterministically.

Applied to agent security:

**Traditional HITL: Cost = O(n) per runtime decision.**
Every request potentially requires human attention. Every approval costs the same. Scale breaks the model.

**Design-Time HITL: Cost = O(log n) per design iteration covering n decisions.**
Each design-time iteration covers exponentially more runtime cases. The system improves through deterministic artifacts, not through scaling human attention.

## Three Modes, Not One

The industry talks about "human-in-the-loop" as if it's a single concept. It's actually three distinct modes with radically different economics:

**Mode 1: Design-Time Human (Scales).** The human reviews and approves World Manifests defining the agent's universe, taint propagation rules, capability matrices per trust level, LLM-generated parsers and canonicalizers, escalation thresholds. One design-time decision amortizes across thousands of runtime decisions.

**Mode 2: Runtime Human — Exception, Not Rule.** The `require_approval` decision is an escape hatch for cases that design-time didn't fully cover. Not the primary path — the pressure relief valve. A critical signal: if `require_approval` fires frequently, the World Manifest is underdefined. This isn't failure — it's a feedback signal that triggers design-time iteration.

**Mode 3: Iteration-Time Human (Feedback Loop).** Runtime logs reveal patterns: "47 requests this week escalated on rule X." "12 taint propagation ambiguities on transformation Y." "Zero bypasses on parser set Z." The human analyzes patterns. The LLM generates updated parsers and rules. Tests run. Deployment follows. Runtime escalations drop. The system learns — through deterministic artifacts, not through stochastic adaptation.

This is precisely the model that made classical hypervisors viable. VMware engineers did not sit beside every VM. They designed isolation rules once, and VMs scaled without human intervention.

## The Evidence Is Already Here

Look at where the industry is independently arriving at this model:

**SOC bounded autonomy** compresses response times by letting AI handle triage automatically while humans approve containment. Graph-based detection shows relationships between events. AI-driven triage achieves over 98% agreement with human expert decisions while cutting manual workloads by more than 40 hours per week. The design-time decision — which categories are autonomous — does the heavy lifting.

**OpenClaw's 48-hour weaponization timeline** proves runtime-only oversight fails. The tool went from 0 to 180,000 GitHub stars. Infostealers added it to their target lists before most security teams knew it was running. Supply chain attacks reached developers in hours. By the time a human reviewer would catch the issue, thousands of instances were compromised. The only viable defense is design-time: define what the agent's world contains before deployment, not after weaponization.

**CX platform security gaps** show what happens when design-time boundaries are absent. Qualtrics processes 3.5 billion interactions annually. When an AI engine triggers a compensation adjustment based on poisoned sentiment data, the damage isn't a security incident — it's a wrong business decision executed at machine speed. No amount of runtime review catches poisoned data flowing through approved API calls. The boundary must exist before the data reaches the AI engine.

**Anthropic's Opus 4.6 SHADE-Arena results** show the agent evading its own maker's monitor 18% of the time. The model built by Anthropic evades the monitor built by Anthropic. If the agent can reason about its own oversight, runtime monitoring has a ceiling. Design-time constraints — what the agent can access, what actions exist in its world — don't depend on the agent cooperating with oversight.

## The Four-Phase Cycle

The Design-Time HITL model operates as a cycle:

**Design.** Human + LLM co-create the World Manifest. LLM generates action schemas, trust policies, taint rules, canonicalization logic. Human reviews and commits.

**Compile.** The World Manifest Compiler transforms the manifest into deterministic artifacts — policy tables, JSON schemas, taint matrices, capability graphs. No LLM survives this phase. All artifacts are unit-testable.

**Deploy.** Runtime executes purely deterministic compiled artifacts. No LLM on the critical path. No human in the loop. Decisions are reproducible and auditable.

**Learn.** Runtime logs accumulate. Escalation patterns emerge. Coverage gaps become visible. Metrics quantify deterministic coverage vs. exception rate.

**Redesign.** Human reviews patterns. LLM generates updated manifest elements. Adversarial testing validates. The manifest is recompiled. The cycle repeats with higher coverage.

As the system matures, the share of `require_approval` decisions trends toward zero. Deterministic coverage trends toward completeness. Human effort concentrates on novel edge cases rather than routine decisions.

## Why This Matters Now

Dario Amodei expects continuous learning for AI agents within 1–2 years. When that arrives, the economics shift permanently. An agent that learns from contaminated data doesn't just process one bad input — it carries that contamination into every future interaction.

Today, a poorly supervised agent can be reset. Tomorrow, a poorly supervised agent with continuous learning cannot. Memory poisoning becomes permanent corruption. The cost of getting design-time boundaries wrong scales from "incident" to "irrecoverable."

The window to build design-time governance infrastructure — World Manifests, compilation pipelines, provenance tracking for learning gates — is measured in months, not years. The organizations that build this now will have the foundation to deploy continuous learning safely. The ones that don't will face Gartner's prediction firsthand: canceled projects, unclear governance, trust destroyed.

The 40% cancellation rate Gartner predicts isn't a technology failure. It's a governance architecture failure. And governance architecture is exactly what design-time HITL solves.

---

**Next in the series:** *"MCP, OpenClaw, and the Missing Virtualization Layer"* — why tool integration without a hypervisor is the biggest unmanaged attack surface in enterprise AI.

*Open-source proof of concept: [Agent Hypervisor](https://github.com/sv-pro/agent-hypervisor)*

*Disclaimer: Personal project. Does not represent Radware's position.*

#AISecurity #AgentSecurity #Cybersecurity #AIGovernance #HumanInTheLoop