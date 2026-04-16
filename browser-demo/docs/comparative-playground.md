# Comparative World Playground

Phase 4 adds a side-by-side experimental lab for comparing two governed worlds under identical conditions.

---

## Why Compare Worlds?

> "I am not comparing policies. I am comparing realities."

The same agent, same page, same intent — but different worlds. The Comparative Playground makes this visible and concrete.

Key questions it answers:
- What changes when the world changes?
- Which actions disappear or appear?
- How does the same attack behave in two worlds?
- Which world is more restrictive, more permissive, or more approval-heavy?

---

## How to Use

1. Open the side panel and click **Compare**
2. Select **World A** and **World B** — choose from built-in presets or use quick matchup buttons
3. Select a **scenario** — curated attack scenarios, or define a custom input
4. View results in three tabs:
   - **Decision** — side-by-side policy decisions with divergence explanation
   - **Action Surface** — full action table showing which decisions differ
   - **Summary** — neutral tradeoff observations, exportable as Markdown

---

## Curated Scenarios

| Scenario | What it shows |
|----------|---------------|
| Hidden page instruction → export | Strict worlds deny; permissive worlds may ask |
| Memory poisoning attempt | Strict: deny; Balanced: ask; Quarantine: ask |
| Benign summarize | All sensible worlds allow — demonstrates preserved utility |
| Tainted content export | Shows taint-handling differences between worlds |
| Trusted source memory write | Should be allowed in all well-formed worlds |

---

## Quick Matchups

| Matchup | Purpose |
|---------|---------|
| Strict vs. Balanced | Shows strictening effect on memory writes |
| Balanced vs. Permissive | Shows relaxation of approval friction |
| Strict vs. Memory Quarantine | Shows quarantine semantics vs. outright denial |

---

## Action Surface

The Action Surface panel shows what every action resolves to in each world, for the current scenario context. It reveals **ontological differences** — some actions exist (are reachable) in one world but not the other.

Same context. Different worlds. Different action space.

---

## Divergence Explanation

When decisions differ, the "Why they differ" section explains:
- Which stage diverged (taint propagation vs. decision rule vs. fallback)
- What each world's state was at that stage
- The structural cause (different rule, missing rule, different trust assignment)

All explanations are derived from manifest structure — no AI-generated commentary.

---

## Export

Click **Export MD** to copy a Markdown comparison report to clipboard. Useful for talks, docs, and design reviews.
