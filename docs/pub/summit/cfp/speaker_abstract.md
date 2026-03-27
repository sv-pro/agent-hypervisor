# Speaker Summary

**Talk:** From Behavior to Boundaries: Compiling Observed Agent Execution into Least-Privilege Worlds

---

Agentic AI systems accumulate effective capability opportunistically — through discovered tools, runtime approvals, and task variability — creating scope creep and undefined execution boundaries. This talk presents a practical pipeline for turning that problem around.

The pattern is: **Observe → Profile → Manifest → Enforce**. Execution traces are recorded from agent/tool activity. A profiler derives a minimal capability profile from observed benign behavior, using a bootstrap trust model to classify input sources and derive taint deterministically. A compiler translates the profile into a declarative World Manifest. A deterministic policy engine evaluates steps against that manifest, returning `ALLOW`, `DENY`, or `REQUIRE_APPROVAL`.

The central value: a manifest derived from observed execution is evidence-backed, not guessed. Design-time capability boundaries become reproducible and reviewable. A hand-written manifest is an assumption about what a workflow needs; a derived manifest is grounded in what the workflow actually did.

A minimal PoC demonstrates the full pipeline on a repository-maintenance scenario, including taint propagation through execution dependencies and deterministic denial of unsafe actions.

---

*~150 words*
