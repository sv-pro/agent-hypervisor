# Crutch / Workaround / Bridge — Content Assets

*Ready-to-use content for LinkedIn, Twitter/X, and talks.*
*Source framework: [docs/positioning/crutch_workaround_bridge.md](../positioning/crutch_workaround_bridge.md)*

---

## 1. LinkedIn Post

---

**Every AI security approach falls into one of three categories. Most are the wrong one.**

🔴 **Crutch** — treats symptoms. Probabilistic. Bypassable. Doesn't change the architecture. New attack = new rule = permanent treadmill.

Examples: prompt injection filters, LLM-as-judge, output scanners.

🟡 **Workaround** — solves today's problem. Partial protection. Production-usable. Still operates inside an architecturally unsafe pipeline.

Examples: tool allow/deny lists, runtime monitoring, LangChain security layers.

🟢 **Bridge** — changes what can exist, not what is permitted. Structural. Deterministic. Attack surface reduced before the agent encounters it.

The key question isn't "Can we stop this attack?"

It's: **"Can this action exist in this world?"**

Most AI security asks the first question. It's the wrong question.

When you filter, you're downstream of the problem. The dangerous action was already expressible. You're trying to catch it after the LLM was persuaded to produce it.

When you define the world, you're upstream. The dangerous action was never expressible. There's nothing to catch.

This is why 12 AI defenses broke in the last 6 months. They were Crutches and Workarounds applied to a pipeline that was architecturally unsafe to begin with.

The fix isn't better filters. It's a different abstraction layer.

**Agent Hypervisor does not block unsafe behavior.**
**It defines a world where unsafe behavior does not exist.**

---

## 2. Twitter/X Thread

---

**Tweet 1**
AI security approaches fall into three categories. Most are the wrong one. A thread. 🧵

**Tweet 2**
🔴 Crutch: treats symptoms, not cause.
Probabilistic. Bypassable. Doesn't change architecture.
New attack = new rule. Permanent treadmill.
Examples: prompt filters, output scanners, LLM-as-judge.

**Tweet 3**
🟡 Workaround: solves the immediate problem.
Partial protection. Production-usable.
Still operates inside an unsafe pipeline.
Examples: tool allow/deny lists, runtime monitoring, LangChain security layers.

**Tweet 4**
🟢 Bridge: changes what can *exist*, not what is *permitted*.
Structural. Deterministic.
Attack surface removed before the agent encounters it.
Examples: capability-based systems, ontology-first architectures.

**Tweet 5**
The difference comes down to one question.

Crutch/Workaround: "Can we stop this attack?"
Bridge: "Can this action exist in this world?"

First question is reactive. Second is generative.

**Tweet 6**
Why does this matter?

When you filter, you're *downstream* of the problem.
The dangerous action was expressible.
You're catching it after the LLM was already persuaded to produce it.

**Tweet 7**
When you define the world, you're *upstream*.
The dangerous action was never expressible.
There's nothing to catch.

`send_email(to, body)` doesn't exist → prompt injection has no target.
Not blocked. Absent.

**Tweet 8**
This is why 12 AI defenses broke last year.
They were Crutches and Workarounds applied to a structurally unsafe pipeline.

You can't patch your way out of an architectural problem.

**Tweet 9**
The Crutch/Workaround treadmill:
→ New attack found
→ New rule added
→ Rule evaded
→ New rule added
→ ...

Coverage is fixed. Attack surface grows. Gap widens.

**Tweet 10**
The Bridge model:
→ Define the agent's world
→ Compile it into deterministic artifacts
→ Agent can only operate within that world
→ New capability added → automatically governed

Coverage grows with the manifest. No per-attack maintenance.

**Tweet 11**
Honest caveat: Bridge approaches have a semantic gap.
The manifest must be correct. Bad manifest = bad security.
This is a *known, bounded* risk — not "zero risk."

Crutches have unknown, unbounded risk.
That's the real comparison.

**Tweet 12**
Agent Hypervisor is a Bridge.

It does not block unsafe behavior.
It defines a world where unsafe behavior does not exist.

Full framework: [link to crutch_workaround_bridge.md or article]

---

## 3. Talk Slide (1 Slide Version)

---

**Slide Title:** Three Categories. Most AI Security Is the Wrong One.

---

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   🔴 CRUTCH              🟡 WORKAROUND           🟢 BRIDGE      │
│                                                                  │
│   Treats symptoms        Solves today's          Changes what   │
│   Probabilistic          problem                 can exist      │
│   Bypassable             Partial protection      Structural     │
│   Permanent treadmill    Bounded scope           Deterministic  │
│                                                                  │
│   prompt filters         tool allow/deny         World Manifest │
│   output scanners        runtime monitoring      capability     │
│   LLM-as-judge           LangChain security      rendering      │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   CRUTCH/WORKAROUND ASK:         BRIDGE ASKS:                   │
│   "Can we stop this attack?"     "Can this action exist         │
│                                   in this world?"               │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Agent Hypervisor does not block unsafe behavior.              │
│   It defines a world where unsafe behavior does not exist.      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Speaker note:** The distinction is not about how good the filter is. It's
about where in the pipeline you operate. Crutches and Workarounds are
downstream of the problem. A Bridge is upstream of it.

---

## Usage Notes

**LinkedIn post** — use as-is or trim to ~800 words for LinkedIn's algorithm.
Remove the ASCII title decoration. End with a question to drive engagement.

**Twitter/X thread** — post as a numbered thread (1/12 through 12/12).
Tweets 2–4 can be posted as a standalone 3-tweet summary thread separately.
Tweet 8 ("12 AI defenses broke") is the highest-engagement standalone tweet.

**Talk slide** — this is a framework introduction slide, not a conclusion slide.
Use it early in a talk to establish the vocabulary. Follow with specific examples
from your audience's domain. The bottom statement is the slide's takeaway.

**Article hook** — the three-line summary works as a section header or pull quote:

> Crutch = filters behavior
> Workaround = controls execution
> Bridge = defines reality
