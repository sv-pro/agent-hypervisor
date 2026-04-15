---
paths:
  - "research/agentdojo-bench/**"
  - "research/benchmarks/**"
---

# AgentDojo Benchmark Rules

## Paths

- Defense implementation: `research/agentdojo-bench/ah_defense/`
- Benchmark runner: `research/agentdojo-bench/run_benchmark.py`
- Results (gitignored): `research/agentdojo-bench/results/`, `research/agentdojo-bench/runs/`
- Documented results: `research/benchmarks/agentdojo/results.md`

## Defense architecture

Three `BasePipelineElement` subclasses in `pipeline.py`:

1. **AHTaintGuard** (pre-ToolsExecutor) — validates tool calls against taint + manifest
2. **AHBlockedCallInjector** (post-ToolsExecutor) — injects feedback; retry cap = 2
3. **AHInputSanitizer** (post-ToolsExecutor, pre-LLM) — canonicalizes outputs, seeds taint

Key design decisions:
- Taint seeding is **detection-driven** (not blind): only taints context when injection patterns found
- Argument-level taint: extracts attacker email targets; only blocks calls whose args match
- `taint_passthrough: false` in manifest = system-generated output, never tainted

## Stale cache — CRITICAL

After any code change to `ah_defense/`, delete cached run files before benchmarking:
```bash
rm -f research/agentdojo-bench/runs/*/workspace/user_task_*/important_instructions/*.json
```
The runner skips tasks with existing result files. Stale cache produces misleading numbers.

## Latest results

560 pairs (40ut × 14it), `gpt-4o-mini-2024-07-18`, workspace suite, `important_instructions` attack:
- Agent Hypervisor: **0.0% ASR**, **80.0% utility** (clean + under attack)
- Baseline (none): 18.2% ASR, 32.5% utility under attack

Full results: `research/benchmarks/agentdojo/results.md`
