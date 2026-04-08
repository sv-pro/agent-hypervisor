# Publications Plan

Two series. Two audiences. One underlying system.

---

## Series 1 — "The Missing Layer" (continuation, articles 5–7)

**Status:** Articles 1–4 published. Series complete through "where to start."
**Audience:** Security practitioners, architects, technical leads evaluating agent security posture.
**Tone:** Architectural, evidence-grounded, cites industry research. No code. Clear analogies.
**Companion artifact:** Whitepaper + benchmark report (`benchmarks/reports/report-v1.md`).

The existing series establishes the thesis. Articles 5–7 deliver the proof.

---

### Article 5 — "The World Manifest: A Spec You Can Read in 10 Minutes"

**TOC:**
1. The document where all design-time decisions live
2. Walkthrough: the email-safe-assistant manifest section by section
   - actions (what exists in this world)
   - capability_matrix (who can do what)
   - taint_rules (what poisons what)
   - escalation_conditions (what requires approval)
   - budgets (hard session limits)
3. What the compiler does with it (8 deterministic artifacts)
4. One YAML file. One human review. Everything else is deterministic.

**Description:** Bridges Part 4's "where to start" to the actual implementation without requiring the reader to open the repo. Shows what a real manifest looks like for the email exfiltration scenario. Makes the World Manifest legible to a non-compiler audience. The core claim: this is the complete physics of the agent's world — not a config file, a contract.

---

### Article 6 — "Five Checks, Zero Surprises: Inside the Deterministic Policy Engine"

**TOC:**
1. Why probabilistic security boundaries are wrong
2. The 5-check evaluation chain
   - Ontology: does this tool exist?
   - Capability: does this trust level permit it?
   - Taint: is this data trying to cross a containment boundary?
   - Escalation: does this action require approval?
   - Budget: are session limits exhausted?
3. The reason chain — every decision is fully auditable
4. Walking the email exfiltration attack through all five checks
5. "The same input always produces the same decision" — why this is not a feature, it's a requirement

**Description:** Most agent security systems are probabilistic. This article explains why that's unacceptable for a boundary and what the alternative looks like in concrete terms. Uses the email exfiltration attack as the running example, showing exactly where in the chain it dies and why. Makes the determinism claim real rather than asserted.

---

### Article 7 — "100% Containment, 0% False Denies: The Benchmark"

**TOC:**
1. What an honest benchmark looks like
2. The scenario taxonomy: attack, safe, ambiguous
3. The baseline comparison: what happens without the hypervisor
4. Results: attack containment rate, false deny rate, latency overhead
5. Honest limitations: 9 scenarios, bounded threat model, PoC not production
6. What it would take to strengthen the claim
7. The next iteration

**Description:** Every previous article references an "executable proof." This article cashes that check. Reports benchmark results honestly with the baseline comparison alongside hypervisor results. The baseline column is the argument — attacks succeed without the boundary, nothing is over-blocked with it. Addresses limitations directly: this is a PoC, the claim is bounded, broader coverage requires more scenarios. Points to the live repo for replication.

---

## Series 2 — "Taint"

**Status:** New series, not started.
**Audience:** Engineers actively building agents — not security researchers, not architects. People who have already shipped an agent that reads from external sources and are vaguely worried.
**Tone:** Bottom-up, operational, code-adjacent. Shorter articles. Direct.
**Companion artifact:** Interactive playground (`http://localhost:8000`) — every article points to it.

Where "The Missing Layer" is top-down and architectural, "Taint" is bottom-up and immediate. The three articles are standalone but build on each other.

---

### Article 1 — "Your Agent Has a Trust Problem (And It's Not the LLM)"

**TOC:**
1. The problem nobody has named yet
2. What agents actually do with input: everything arrives as a string
3. Email content, web text, tool outputs, user instructions — all identical to the runtime
4. The missing primitive: a type system for trust
5. The taint bit — the simplest possible formalization
6. What changes when you add it

**Description:** Not about hallucination or alignment. About the structural fact that agents mix trusted and untrusted data in the same context and treat it identically. Every engineer who has built an agent that reads from external sources has this problem right now — they just don't have a name for it. This article names it. Ends with the taint bit as the minimal formalization, setting up the next two articles.

---

### Article 2 — "Taint Propagation: The Rule Your Agent Needs But Doesn't Have"

**TOC:**
1. Information flow security — a 50-year-old idea your agent should borrow
2. How taint propagates: untrusted input → tainted event → tainted proposal → blocked at boundary
3. The key insight: taint is structural, not content-based
4. Why you can't escape it by rephrasing the input
5. Try it yourself — the interactive playground
6. What retrofitting a taint bit looks like in an existing pipeline

**Description:** Borrows information flow security from OS security and applies it directly to agent pipelines. The central claim — taint is structural, not content-based — is the thing that makes this different from a prompt filter. You can't bypass it by rephrasing. Points to the playground as an interactive proof: "try to send a tainted email externally. You can't. That's the point." Includes a section on retrofitting — engineers can add a basic taint bit in an afternoon.

---

### Article 3 — "The Three Laws of Tainted Data"

**TOC:**
1. Why "don't trust external input" is not a law, it's advice
2. Law 1: Taint is initialized at the channel, not inferred from content
3. Law 2: Taint propagates monotonically — it can only increase
4. Law 3: Tainted data cannot cross a trust boundary without a named sanitization gate
5. What each law looks like in code
6. What breaks when you violate each one (with examples)
7. These aren't novel — this is information flow security applied to a new domain

**Description:** Distills the architecture into three rules that any system must satisfy to contain tainted data. Each law is stated precisely, illustrated with the email exfiltration scenario, and shown to break a specific class of attack when enforced. The article ends by locating these laws in the longer history of information flow security — not as a novelty claim, but as legitimacy: this pattern has worked in OS security for decades.

---

## Sequencing

```
Now                          Next                         Later
─────────────────────────────────────────────────────────────────
Missing Layer 5              Missing Layer 6              Missing Layer 7
(World Manifest)             (Policy Engine)              (Benchmark)

Taint 1                      Taint 2                      Taint 3
(Trust Problem)              (Propagation)                (Three Laws)
```

The two series run in parallel. "The Missing Layer" continuations point to the benchmark report and the repo. "Taint" points to the playground. Each series stands alone but both funnel to the same underlying system.

---

## What is not planned here

- Social media (threads, tweets) — handled separately, derived from articles
- Platform-specific adaptations (LinkedIn, HackerNews, Dev.to) — handled per article
- Full whitepaper — separate document, already in progress
