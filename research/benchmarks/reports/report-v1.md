# Agent Hypervisor — Benchmark Report v1

**Trace:** `run-20260309T181343.jsonl`

## Scenario coverage

| Class | Count |
|-------|-------|
| attack | 4 |
| safe | 3 |
| ambiguous | 2 |
| **total** | **9** |

## Security metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Attack containment rate | 100.0% | Fraction of attack scenarios correctly denied |
| Taint containment rate | 100.0% | Tainted data never reaches external_write |
| False deny rate | 0.0% | Safe scenarios incorrectly blocked (lower is better) |
| False escalation rate | 0.0% | Safe scenarios escalated when allow was correct (lower is better) |

## Utility metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Task completion rate | 100.0% | Safe+ambiguous scenarios reaching allow or require_approval |
| Deterministic coverage | 100.0% | Scenarios with concrete verdict (no errors) |
| Latency overhead | 0.561 ms | Mean extra latency added by hypervisor vs baseline |

## Comparison: hypervisor vs baseline

| Mode | Correct | Total | Notes |
|------|---------|-------|-------|
| Hypervisor | 9 | 9 | Full policy enforcement |
| Baseline | 3 | 9 | No boundary — attacks succeed |

## Interpretation

- A **100% attack containment rate** means all tested attack patterns were blocked.
- A **0% false deny rate** means legitimate requests were not blocked.
- The baseline's low score on attack/ambiguous scenarios demonstrates the value of the boundary.
- These metrics can be recomputed after any manifest or compiler change by re-running the benchmark.
