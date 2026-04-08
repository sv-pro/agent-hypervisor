# Microsoft Copilot Ignored "Confidential" Labels for 4 Weeks. No DLP Caught It. Here's the Architectural Root Cause.

*Personal analysis — does not represent Radware's position*

---

## The Incident

For four weeks starting January 21, 2026, Microsoft 365 Copilot Chat read and summarized emails marked "Confidential" — despite sensitivity labels and DLP policies explicitly configured to prevent it.

The enforcement broke inside Microsoft's own pipeline. No EDR, no WAF, no security tool in the stack flagged it. The UK's National Health Service logged it as a security incident. Microsoft tracked it as CW1226324.

This was the **second time in eight months**. In June 2025, Aim Security discovered EchoLeak (CVE-2025-32711) — a zero-click attack where a single malicious email bypassed Copilot's prompt injection classifier, accessed internal data, and exfiltrated it to an attacker-controlled server.

Two incidents. Two completely different vectors — one a code bug, one a prompt injection attack. Same root cause.

## The Pattern: Permission Security Fails When Platforms Break

Here's what happened architecturally:

```
[ Sensitivity Labels ]  ← configured correctly ✓
[ DLP Policies ]         ← configured correctly ✓  
[ Access Controls ]      ← configured correctly ✓
[ Copilot Retrieval ]    ← bug in code path
         ↓
[ Confidential emails enter AI context ]
         ↓
[ All downstream controls bypassed ]
```

Every security control — labels, DLP, access restrictions — lived **inside** the same platform as the AI. When the platform broke, everything broke simultaneously.

Aim Security's researchers described it precisely: agents process trusted and untrusted data in the same thought process, making them **structurally vulnerable** to manipulation.

This isn't a Microsoft problem. It's an architectural pattern problem.

## The Question Nobody Is Asking

The industry response is predictable:
- "Configure DLP better"  
- "Add monitoring layers"  
- "Audit your labels"

All of these ask the same question: **"Can Copilot access this data?"** — and answer with a runtime permission check.

But CW1226324 proved that runtime permission checks fail when the platform has a bug. And EchoLeak proved they fail when an attacker is clever enough. Two different failure modes. Same architectural weakness.

The question we should be asking:

> **"Does confidential data exist in Copilot's retrieval universe at all?"**

Not "is it forbidden?" — but "is it present?"

## The Clue Hidden in Microsoft's Own Fix

Here's the interesting part. Among Microsoft's own recommendations was **Restricted Content Discovery (RCD)**: remove sensitive SharePoint sites from Copilot's retrieval pipeline entirely.

RCD works regardless of whether the trust violation comes from a code bug or an injected prompt — because the data **never enters the context window** in the first place.

This is not a permission check. This is removal from the world. And it works precisely because it answers a different question:

- Permission: "Is Copilot allowed to see this?" → can fail
- Ontological: "Does this exist in Copilot's world?" → if it doesn't exist, there's nothing to fail

RCD is, in effect, a primitive form of what I've been calling **Input Virtualization** — the idea that AI agents should never perceive raw reality, but only a curated, deterministic subset of it.

## From Ad Hoc to Architecture

RCD works for SharePoint. But what about emails? Files? MCP tool outputs? API responses? Every new data source creates a new path that must be independently secured — and independently auditable.

The pattern I've been exploring with Agent Hypervisor formalizes this into an architecture:

```
[ Raw Reality — emails, files, APIs, tools ]
              ↓
[ Virtualization Boundary — deterministic, testable ]
              ↓
[ Agent's World — only what's defined exists ]
```

Key principles:

**Input Virtualization:** Raw data is transformed into structured Semantic Events with source, trust level, and provenance metadata — before the agent perceives anything. Hidden instructions are stripped at the boundary, not detected after ingestion.

**Taint Propagation:** Data from untrusted sources carries contamination status as a physical property of the agent's world. Tainted data cannot cross external boundaries — not by rule (which can have bugs), but by construction (the operation doesn't exist).

**Deterministic Enforcement:** Security decisions are pure functions — same input, same decision, always. No LLM on the critical security path. Fully unit-testable. An attacker cannot "learn" to bypass deterministic physics.

**Provenance Tracking:** Every object knows its origin chain. Critical for continuous learning safety: only data with verified provenance enters the learning loop.

## Why the Copilot Bug Matters Beyond Microsoft

This incident validates three things:

**1. Permission-based security is architecturally fragile.**
Labels and DLP are *descriptions of intent*. They work when every component in the stack honors them. One code path error — and the entire model collapses. For four weeks. Silently.

**2. Detection-based approaches have a blind spot.**
No EDR, WAF, or SIEM caught either incident. When the AI agent itself is the vector, traditional detection tools don't have visibility into what the agent perceives — they only see network-level artifacts.

**3. The retrieval boundary is the critical seam.**
As one analysis noted: the retrieve-then-generate architecture is powerful and fragile because the enforcement checkpoint must occur at retrieval. If retrieval fails, everything downstream is compromised.

This is exactly the thesis behind Agent Hypervisor: the **virtualization boundary** — the layer between raw reality and the agent's perception — is the only point where security can be both deterministic and complete.

## What You Can Do Today

While architectural solutions mature, there are practical steps:

- **Enable RCD** for SharePoint sites with sensitive data — it's the closest thing to Input Virtualization available today
- **Audit retrieval paths**, not just access permissions — what can the AI *actually pull* vs what policies *say* it can pull
- **Tag inputs by source and trust level** — even a simple classification layer helps (30 minutes to implement)
- **Separate governance from the governed platform** — if your only controls live inside the AI platform, a platform bug = total control failure
- **Log what the AI accesses, not just what users do** — build independent audit trails for AI data ingestion

## The Bigger Picture

Dario Amodei (Anthropic CEO) recently stated that continuous learning for AI agents is expected within 1-2 years. When that arrives, incidents like CW1226324 become permanent — the AI doesn't just read the confidential email once, it *learns from it* and carries that contamination forward.

The window to build architectural boundaries — not better labels, not smarter filters, but fundamentally different trust models — is narrow and closing.

We're surprised when these incidents happen. We shouldn't be. Given the current architecture — raw retrieval + inline enforcement + no independent boundary — they're not bugs. They're physics.

---

*I'm exploring these ideas in an open-source proof of concept: [Agent Hypervisor](https://github.com/sv-pro/agent-hypervisor) — deterministic virtualization of reality for AI agents. Feedback welcome.*

*Disclaimer: Personal project and analysis. Does not represent Radware's position. References to published research only.*

---

#AISecurity #AgentSecurity #Cybersecurity #Microsoft365 #Copilot #DLP #PromptInjection #AIGovernance