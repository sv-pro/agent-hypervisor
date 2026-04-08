---
name: benchmark
description: Run the AgentDojo benchmark for the Agent Hypervisor defense
argument-hint: "[--suite workspace|travel] [--no-attack] [--all-defenses] [--model MODEL]"
---

Run the AgentDojo benchmark with: $ARGUMENTS

Working directory: `research/agentdojo-bench/`
Default model: `gpt-4o-mini-2024-07-18`
Default suite: `workspace`
Default defense: `agent_hypervisor`
Default attack: `important_instructions`

Common invocations:
```bash
# Full AH benchmark, workspace suite, with attack
cd research/agentdojo-bench && python run_benchmark.py \
    --model gpt-4o-mini-2024-07-18 --suite workspace \
    --defense agent_hypervisor --attack important_instructions

# No-attack utility baseline
cd research/agentdojo-bench && python run_benchmark.py \
    --model gpt-4o-mini-2024-07-18 --suite workspace \
    --defense agent_hypervisor --no-attack

# All defenses comparison
cd research/agentdojo-bench && python run_benchmark.py \
    --model gpt-4o-mini-2024-07-18 --suite workspace \
    --all-defenses --attack important_instructions
```

Results are saved to `research/agentdojo-bench/results/` (gitignored).
Documented results: `research/benchmarks/agentdojo/results.md`

**Before running**: ensure `OPENAI_API_KEY` is set in `research/agentdojo-bench/.env`

**Stale cache warning**: after any defense code change, delete cached run files:
```bash
rm -f research/agentdojo-bench/runs/*/workspace/user_task_*/important_instructions/*.json
```
Otherwise the runner skips tasks using old cached results and reports stale numbers.
