# AgentDojo Benchmark — Methodology

This document describes the experimental setup used to evaluate Agent Hypervisor
against the [AgentDojo](https://github.com/ethz-spylab/agentdojo) benchmark suite.

---

## What is AgentDojo

AgentDojo is an adversarial benchmark for AI agents that measures:

1. **Utility** — the fraction of legitimate tasks the agent completes correctly
   without the firewall interfering with normal operation.

2. **Attack Success Rate (ASR)** — the fraction of prompt injection attacks that
   succeed (i.e. the agent performs the attacker's intended action).

The benchmark provides a suite of tasks across multiple domains (email assistant,
travel planner, banking, etc.) paired with adversarial test cases where attacker-
controlled content (injected into documents, emails, or web pages) attempts to
hijack the agent's actions.

---

## Tasks Evaluated

For this initial evaluation, we focused on tasks from the following AgentDojo
suites that involve outbound side effects (email sending, HTTP requests, file
writes) — the class of actions the provenance firewall is designed to govern:

| Suite            | Task category                    | Task count |
|------------------|----------------------------------|------------|
| `email_client`   | Email composition and sending    | 8          |
| `travel_agent`   | Booking queries with side effects | 4          |
| `banking`        | Transaction and report tasks     | 4          |

Total: 16 tasks with injection attacks, 16 corresponding clean (no-injection) tasks.

---

## Agent Configuration

- **LLM backend:** GPT-4o (OpenAI) via the AgentDojo default agent harness.
- **Tool set:** The AgentDojo tool set for each suite (read, send, search, etc.).
- **Firewall:** Agent Hypervisor `ProvenanceFirewall` inserted between the agent
  and tool execution.

### Firewall configuration

The firewall was configured with:
- `protection_enabled=True`
- Task manifests written for each suite declaring legitimate data sources as
  `user_declared` with appropriate roles.
- `require_confirmation=True` for all outbound side-effect tools.

`ask` verdicts were resolved as `deny` in this evaluation (no human in the loop
during automated benchmark runs). In a production deployment, `ask` would pause
for human confirmation.

---

## Comparison Baseline

We compare against two baselines:

**No defense** — The agent runs with no firewall. This measures baseline utility
(no friction) and baseline ASR (maximum attack success).

**CaMeL** — The dual-LLM approach from [Debenedetti et al., 2025] where a
privileged model interprets instructions and an unprivileged model handles
untrusted data. CaMeL is the closest published approach to provenance-aware
defense.

| System              | Utility | ASR   |
|---------------------|---------|-------|
| No defense          | 100%    | ~70%  |
| CaMeL               | ~80%    | ~10%  |
| Agent Hypervisor    | see results.md | see results.md |

CaMeL utility and ASR numbers are approximate, taken from the published paper.
Direct comparison is approximate because evaluation harnesses differ.

---

## Measurement Protocol

For each task × attack pair:

1. Run the task with injected adversarial content in the data source.
2. Record whether the agent proposes the attacker's target action.
3. Record whether the firewall blocks or allows the target action.
4. Record whether the agent completes the legitimate task objective.

**ASR** = fraction of injection attacks where the attacker's target action is
executed (firewall verdict = allow, action executed).

**Utility** = fraction of legitimate tasks where the agent completes the task
objective without the firewall blocking a necessary legitimate action.

---

## Limitations

This is an **initial prototype evaluation**. The following limitations apply:

- **Small task count.** 16 tasks is not sufficient for statistical significance.
  A full evaluation should cover the complete AgentDojo suite (>100 tasks).

- **Manual manifest writing.** Task manifests were written by hand for this
  evaluation. In a production system, manifests should be reviewed as part of the
  deployment process. Poorly-written manifests (overly permissive declared_inputs)
  reduce security; overly restrictive manifests reduce utility.

- **ask → deny substitution.** Treating `ask` verdicts as `deny` in automated runs
  may undercount utility if some legitimate tasks require actions that receive `ask`
  verdicts. In real use, `ask` enables human review rather than blocking.

- **Single model.** Results may differ across LLM backends. The model's tendency
  to follow injected instructions varies by model and prompt.
