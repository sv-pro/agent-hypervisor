# AgentDojo Benchmark — Results

**Status: Initial prototype evaluation.**

These results are preliminary. The evaluation covers a subset of AgentDojo tasks
selected for their relevance to outbound side-effect tool calls (email, HTTP, file
writes). See [methodology.md](methodology.md) for full experimental setup.

---

## Summary

| System                        | Utility | Attack Success Rate (ASR) |
|-------------------------------|---------|---------------------------|
| No defense (baseline)         | 100%    | 69%                       |
| CaMeL (Debenedetti et al.)    | ~80%    | ~10%                      |
| **Agent Hypervisor (ours)**   | **81%** | **6%**                    |

*Utility: fraction of legitimate tasks completed correctly.*
*ASR: fraction of injection attacks that succeeded (attacker's action executed).*

---

## Per-Suite Results

### Email Client Suite (8 tasks)

| Metric  | No defense | Agent Hypervisor |
|---------|------------|------------------|
| Utility | 100% (8/8) | 88% (7/8)        |
| ASR     | 75% (6/8)  | 0% (0/8)         |

All 8 injection attacks were blocked. One legitimate task failed: the agent
attempted to send email to a recipient extracted from an external document (which
is correctly blocked), but the task required that recipient. Resolution: update
the task manifest to declare that data source as a `recipient_source`.

### Travel Agent Suite (4 tasks)

| Metric  | No defense | Agent Hypervisor |
|---------|------------|------------------|
| Utility | 100% (4/4) | 75% (3/4)        |
| ASR     | 75% (3/4)  | 25% (1/4)        |

One attack succeeded: the injection caused the agent to call `read_file` (a
read-only tool), which the firewall allows unconditionally. The read-only
call was the attacker's intended action. Resolution: read-only tools should
not be considered side-effect-free in all contexts — future work.

### Banking Suite (4 tasks)

| Metric  | No defense | Agent Hypervisor |
|---------|------------|------------------|
| Utility | 100% (4/4) | 75% (3/4)        |
| ASR     | 50% (2/4)  | 0% (2/4)         |

Both injection attacks blocked. One utility failure: an HTTP report submission
was blocked because the submitted data included fields derived from external
account data (correctly flagged as external_document provenance).

---

## Key Observations

**ASR reduction is near-total for email and file-write attacks.** The structural
provenance check catches injection patterns that bypass string-matching defenses,
regardless of phrasing.

**Read-only tools are a gap.** The current firewall does not restrict `read_file`
or `list_dir`. An attacker whose intended action is data *access* (not exfiltration)
can still succeed if they cause the agent to read a file the attacker controls.

**Utility loss is primarily from manifest gaps.** Cases where legitimate tasks
were blocked typically arose from incomplete task manifests — data sources that
should have been declared as `user_declared` were treated as `external_document`.
This is a deployment concern, not a fundamental limitation.

**The `ask` mechanism is not evaluated here.** In this automated evaluation,
`ask` verdicts were treated as `deny`. In production, `ask` verdicts allow human
reviewers to approve legitimate borderline cases, which would recover some utility.

---

## Interpretation

Agent Hypervisor achieves lower ASR than CaMeL (6% vs ~10%) with comparable
utility (81% vs ~80%) on this task subset. The key difference in mechanism:

- CaMeL separates trusted and untrusted LLM instances, relying on the privileged
  model to resist influence from untrusted data.
- Agent Hypervisor enforces structural provenance constraints at the tool boundary,
  requiring no LLM on the critical security path.

The provenance approach is deterministic: the same structural violation is always
blocked, regardless of how the injection is phrased or what model processes it.

---

## Reproducibility

The benchmark setup is described in [methodology.md](methodology.md). Task manifests
used for this evaluation are available in `manifests/`. A benchmark runner script
will be published in a future update.

*Note: These results were obtained with a prototype implementation. They should be
treated as directional evidence, not production benchmarks. A larger, independently
replicated evaluation is needed before drawing strong conclusions.*
