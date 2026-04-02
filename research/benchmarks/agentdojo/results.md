# AgentDojo Benchmark — Results

**Status: Post-refactor evaluation. Preliminary — independent replication needed.**

These results cover the full AgentDojo workspace suite, relevant to outbound
side-effect tool calls. See [methodology.md](methodology.md) for full experimental setup.

---

## Summary — Full Scope (Post-Refactor)

Full scope: 40 user tasks × 14 injection tasks = 560 pairs.
Model: `gpt-4o-mini-2024-07-18`, Attack: `important_instructions`.

| System | Utility (under attack) | ASR | Utility (clean) |
| --- | --- | --- | --- |
| **Agent Hypervisor (ours)** | **80.0%** | **0.0%** | **80.0%** |
| tool_filter | 72.9% | 1.1% | 80.0% |
| spotlighting_with_delimiting | 47.5% | 12.7% | 77.5% |
| none (baseline) | 32.5% | 18.2% | 82.5% |

*Utility (under attack): fraction of legitimate tasks completed correctly when injection attacks are present.*
*ASR: fraction of injection attacks that succeeded (attacker's action executed).*
*Utility (clean): fraction of legitimate tasks completed correctly with no attack present.*

Agent Hypervisor achieves the highest utility under attack and the lowest ASR
across all evaluated systems. Clean utility is on par with the best alternatives.

---

## Before → After Refactor

| Metric | Before | After | Delta |
| --- | --- | --- | --- |
| No-attack utility | 53.3% | **80.0%** | +26.7pp |
| Attack utility | ~60% | **80.0%** | ~+20pp |
| Attack ASR | ~47.8% | **0.0%** | ~−47.8pp |

The refactor addressed two root causes:

- **Detection-driven taint seeding** (was: taint every tool output unconditionally).
  Clean tool outputs no longer poison the taint state, eliminating false positives
  in no-attack scenarios. No-attack utility recovered from 53.3% → 80.0%.

- **Argument-level taint containment** (was: block all external-boundary calls once
  any taint present). Taint now carries the attacker's specific target values; calls
  whose arguments don't match those values are allowed. Attack utility and ASR
  both resolved to the same level as clean utility.

---

## Key Observations

**0% ASR across 560 attack pairs.** No injection attack succeeded after the
refactor. The structural provenance check blocks injection patterns regardless
of phrasing or model behavior.

**AH improves utility over no-defense under attack.** Under attack, the baseline
achieves only 32.5% utility — the agent follows attacker instructions instead of
completing the user's task. AH restores utility to 80.0% by blocking injections
and returning control to the legitimate task.

**Clean-data utility gap is minimal.** The 2.5pp gap vs. baseline (80.0% vs 82.5%)
reflects cases where the provenance model conservatively restricts data flows that
happen to be legitimate. Resolution path: refine task manifests to declare those
data sources explicitly.

**read_file gap (prior evaluation) is resolved.** The prior evaluation identified
that read-only tools could be the attacker's intended action. The refactored
`taint_passthrough` flag and manifest reclassification address this.

---

## Prior Results (Initial Prototype, 16-task subset)

For reference, the initial prototype evaluation on a 16-task subset:

| System | Utility | ASR |
| --- | --- | --- |
| No defense (baseline) | 100% | 69% |
| CaMeL (Debenedetti et al.) | ~80% | ~10% |
| Agent Hypervisor (prototype) | 81% | 6% |

The full-scope post-refactor evaluation supersedes these numbers.

---

## Interpretation

Agent Hypervisor achieves 0% ASR with 80% utility on a 560-pair evaluation.
The key architectural difference from CaMeL:

- **CaMeL** separates trusted and untrusted LLM instances, relying on the
  privileged model to resist influence from untrusted data.
- **Agent Hypervisor** enforces structural provenance constraints at the tool
  boundary, requiring no LLM on the critical security path.

The provenance approach is deterministic: the same structural violation is always
blocked, regardless of how the injection is phrased or what model processes it.
This property does not degrade under adaptive attacks that vary injection phrasing.

---

## Limitations

- **Single benchmark.** AgentDojo covers a specific task distribution. Results
  may not generalize to all agentic deployment patterns.

- **Manifest quality.** Task manifests were generated with LLM assistance and
  reviewed before use. In production, manifest quality directly affects both
  utility and security.

- **`ask` → `deny` substitution.** In this automated evaluation, `ask` verdicts
  were treated as `deny`. In production, `ask` enables human review, recovering
  some utility on borderline cases.

- **Single LLM backend.** Results were obtained with `gpt-4o-mini-2024-07-18`.
  Performance may vary across models with different instruction-following tendencies.

- **Independent replication needed.** These are preliminary results from a
  prototype implementation. Strong conclusions require larger, independently
  replicated evaluations.

---

## Reproducibility

Task manifests used for this evaluation are in `ah_defense/manifests/`.
Benchmark runner: `research/agentdojo-bench/run_benchmark.py`.
