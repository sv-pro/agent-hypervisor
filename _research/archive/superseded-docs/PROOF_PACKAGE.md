# Proof Package — Agent Hypervisor

This document links every narrative claim to a specific executable artifact so the architecture-and-proof system is coherent and verifiable.

---

## The argument

> Agents are unsafe because they act in an unvirtualized reality. The fix is not behavioral constraints on the agent. It is ontological security — virtualizing the world the agent lives in, so that dangerous tools do not exist, tainted data cannot escape, and every decision is deterministic and auditable.

---

## Claim → proof mapping

| Claim | Artifact | How to verify |
|-------|----------|---------------|
| Prompt injection can be contained at the input boundary | `src/boundary/semantic_event.py` | `pytest tests/test_semantic_event.py::TestConformancePattern` |
| Tainted data cannot reach external_write without a gate | `src/policy/engine.py` (taint check) | `pytest tests/test_invariants.py::TestI3TaintInvariant` |
| Tools not in the World Manifest do not exist (not_in_world, not forbidden) | `src/gateway/proxy.py` (virtualization gate) | `pytest tests/test_gateway.py::TestVirtualizedDevices` |
| The policy engine is deterministic (same input → same decision) | `src/policy/engine.py` | `pytest tests/test_invariants.py::TestI4DeterminismInvariant` |
| Irreversible actions require approval, not denial | `manifests/examples/email-safe-assistant.yaml` (escalation_conditions) | `pytest tests/test_invariants.py::TestI6ReversibilityInvariant` |
| Agent cannot upgrade trust or clear taint | `src/boundary/intent_proposal.py` | `pytest tests/test_invariants.py::TestI5SeparationInvariant` |
| Budget limits are hard-enforced | `src/policy/engine.py` (budget check) | `pytest tests/test_invariants.py::TestI7BudgetInvariant` |
| Attack containment rate = 100% on current scenario set | `benchmarks/reports/report-v1.md` | `python benchmarks/runner.py && python benchmarks/metrics.py` |
| Legitimate requests are not over-blocked (false deny = 0%) | `benchmarks/reports/report-v1.md` | `python benchmarks/runner.py` |
| Every decision is fully auditable | `src/provenance/graph.py` | `python benchmarks/replay.py --walkthrough` |
| The Design→Compile→Deploy→Learn→Redesign cycle works end-to-end | `ahc build` + `pytest` + demo | See QUICKSTART.md Step 3 |

---

## Executable proof artifacts

### Tests (deterministic, no LLM)

```bash
pytest tests/                          # 215 tests, all pass
pytest tests/test_invariants.py        # all 7 architectural invariants
pytest tests/test_gateway.py           # all 32 gateway tests
pytest tests/test_policy_engine.py     # policy engine + provenance graph
```

### Demo

```bash
python examples/basic/02_hypervisor_demo.py
```

Shows three scenarios: attack (denied), poisoned tool output (blocked), legitimate workflow (allowed + escalated).

### Benchmark

```bash
python benchmarks/runner.py
python benchmarks/metrics.py
python benchmarks/replay.py --walkthrough
```

Produces `benchmarks/reports/report-v1.md` with 7 security and utility metrics.

### Compiler (determinism check)

```bash
ahc build manifests/examples/email-safe-assistant.yaml -o /tmp/run1 --quiet
ahc build manifests/examples/email-safe-assistant.yaml -o /tmp/run2 --quiet
diff -r /tmp/run1 /tmp/run2   # must be empty
```

---

## Document map

| Document | Purpose | Links to |
|----------|---------|---------|
| [README.md](../README.md) | One-page overview | CONCEPT, QUICKSTART, WHITEPAPER |
| [CONCEPT.md](../CONCEPT.md) | Architecture explainer | ARCHITECTURE, invariants |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Five-layer design reference | src/ module map |
| [docs/QUICKSTART.md](QUICKSTART.md) | 5-minute first run | demo, benchmarks, manifest |
| [manifests/schema.yaml](../manifests/schema.yaml) | World Manifest reference | examples/ |
| [POSITIONING.md](../POSITIONING.md) | What this is and is not | CONCEPT, FAQ |
| [FAQ.md](../FAQ.md) | Common questions | CONCEPT, ARCHITECTURE |
| [THREAT_MODEL.md](../THREAT_MODEL.md) | Threat scope | CONCEPT |
| [ROADMAP.md](../ROADMAP.md) | Milestone plan | PROJECT_TASKS |
| [VERIFICATION_PLAN.md](../VERIFICATION_PLAN.md) | DOD checklist | all issues |
| [benchmarks/reports/report-v1.md](../benchmarks/reports/report-v1.md) | Current benchmark results | runner, metrics |

---

## What is not claimed

- This does not prevent all possible attacks — only those within the defined threat model.
- The benchmark covers 9 scenarios; broader coverage requires more scenario fixtures.
- The latency overhead is sub-millisecond on current hardware; production deployment may vary.
- The system is a PoC + reference implementation, not a production-hardened platform.

See [POSITIONING.md](../POSITIONING.md) for the full list of non-claims.
