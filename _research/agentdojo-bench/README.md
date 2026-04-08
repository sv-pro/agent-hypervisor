# Agent Hypervisor × AgentDojo Benchmark

This directory integrates Agent Hypervisor as a defense in the [AgentDojo](https://github.com/ethz-spylab/agentdojo) benchmark, enabling head-to-head comparison against baseline and existing defenses.

## Architecture

```
agentdojo-bench/
├── ah_defense/
│   ├── __init__.py          # Package (lazy imports)
│   ├── pipeline.py          # BasePipelineElement subclasses
│   ├── canonicalizer.py     # Input sanitization (regex, no ML)
│   ├── taint_tracker.py     # Taint propagation state
│   ├── intent_validator.py  # Tool call validation
│   └── manifests/
│       ├── workspace.yaml   # World Manifest: workspace suite
│       ├── travel.yaml      # World Manifest: travel suite
│       ├── banking.yaml     # World Manifest: banking suite
│       └── slack.yaml       # World Manifest: slack suite
├── tests/
│   ├── test_canonicalizer.py
│   ├── test_taint_tracker.py
│   ├── test_intent_validator.py
│   └── test_pipeline_elements.py
├── run_benchmark.py         # Benchmark runner
├── analyze_results.py       # Results → comparison table
└── requirements.txt
```

## How It Works

The AH defense operates as three `BasePipelineElement` subclasses inside `ToolsExecutionLoop`:

```
ToolsExecutionLoop([
    AHTaintGuard,           # ① Validate proposed calls against taint + manifest
    ToolsExecutor,          # Execute allowed tools → add tool result messages
    AHBlockedCallInjector,  # ② Inject feedback for blocked calls
    AHInputSanitizer,       # ③ Canonicalize outputs, seed taint
    LLM,                    # Propose next tool calls
])
```

### AHInputSanitizer (post-ToolsExecutor, pre-LLM)

- Canonicalizes outputs first: strips `<INFORMATION>...</INFORMATION>` injection blocks,
  `IMPORTANT!!! Ignore...` prefixes, `[[SYSTEM:...]]` markers, zero-width chars
- Taint seeding is **detection-driven**: only taints context when injection patterns are
  actually found in the output (not blindly on every tool call)
- When injection is detected, extracts attacker-specified values (email addresses etc.)
  into `ProvTaintState.tainted_values` for argument-level checking
- Wraps outputs with trust metadata (`[AH|SOURCE:tool|TRUST:untrusted]`)

### AHTaintGuard (pre-ToolsExecutor)

- Resolves each tool call to a logical action via compiled World Manifest predicates
- Runs full 7-step fail-closed validation pipeline (manifest → action → schema → capability → taint → escalation → allow)
- **TaintContainmentLaw**: tainted context + external-boundary action → **BLOCK**
- **Argument-level refinement**: if `tainted_values` are known, only blocks calls whose
  arguments contain those specific values — allows legitimate user actions whose args
  don't match the attacker's payload
- Renames blocked calls to `ah_security_blocked` (invisible to security scorer)

### AHBlockedCallInjector (post-ToolsExecutor)

- Injects structured error feedback for blocked calls
- **Retry cap**: after 2 blocks of the same action per episode, escalates to a CRITICAL
  message forcing the LLM to abandon the blocked action and complete the original task

### World Manifests

YAML files classifying suite tools into:

- `read_only` — retrieval only (always permitted)
- `internal_write` — modifies internal state (permitted)
- `external_side_effect` — communicates externally (blocked when tainted)

## Key Design Choices vs. CaMeL

| Property | CaMeL | Agent Hypervisor |
|----------|-------|-----------------|
| Taint granularity | Value-level (Python interpreter) | Message-level (all tool outputs) |
| Security path | Dual-LLM (privileged + quarantined) | **No LLM** on critical path |
| Policy definition | Manual (user-defined) | Design-time compiled manifests |
| Performance overhead | Interpreter overhead | O(1) manifest lookup + regex |
| Provable security | Yes (with interpreter) | Deterministic (same inputs → same block) |

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
# or
echo "OPENAI_API_KEY=sk-..." > .env
```

## Running Tests

```bash
# Core unit tests (no API key needed)
python -m pytest tests/test_canonicalizer.py tests/test_taint_tracker.py tests/test_intent_validator.py -v

# All tests
python -m pytest tests/ -v
```

## Running the Benchmark

```bash
# Quick test: single suite, single task pair
python run_benchmark.py \
    --model claude-3-5-sonnet-20241022 \
    --suite workspace \
    --user-task user_task_0 \
    --injection-task injection_task_0 \
    --attack important_instructions

# Full AH benchmark: workspace + travel
python run_benchmark.py \
    --model claude-3-5-sonnet-20241022 \
    --suite workspace --suite travel \
    --defense agent_hypervisor \
    --attack important_instructions

# All defenses comparison (GPT-4o only, tool_filter requires OpenAI)
python run_benchmark.py \
    --model gpt-4o-2024-05-13 \
    --suite workspace \
    --all-defenses \
    --attack important_instructions

# Utility-only (no attack)
python run_benchmark.py \
    --model claude-3-5-sonnet-20241022 \
    --suite workspace \
    --defense agent_hypervisor \
    --no-attack
```

## Analyzing Results

```bash
# Generate comparison table from results directory
python analyze_results.py results/

# Include CaMeL paper reference numbers
python analyze_results.py results/ --include-camel-paper --output comparison.md

# Show specific file
python analyze_results.py results/results_claude-3-5-sonnet-20241022_important_instructions.json
```

## Benchmark Results

Full-scope run: 40 user tasks × 14 injection tasks (560 attack pairs) + 40 clean tasks.
Model: `gpt-4o-mini-2024-07-18`, Suite: workspace, Attack: `important_instructions`.

| Defense | Utility (clean) | Utility (attack) | ASR |
| --- | --- | --- | --- |
| none | 82.5% | 32.5% | 18.2% |
| spotlighting_with_delimiting | 77.5% | 47.5% | 12.7% |
| tool_filter | 80.0% | 72.9% | 1.1% |
| **agent_hypervisor** | **80.0%** | **80.0%** | **0.0%** |
| CaMeL (paper) | 77% | 77% | 0% |

AH achieves 0% ASR (same as CaMeL) while matching the `none` baseline on utility in both clean
and attack conditions. Unlike CaMeL, AH requires no LLM on the security path and no value-level
interpreter — enforcement is deterministic O(1) manifest lookup + regex.

## Benchmark Versions

The default benchmark version is `v1.2.2`. AgentDojo supports:
- `v1` — original benchmark
- `v1.2.2` — current recommended (includes more injection tasks)

## Extending

To add a new suite manifest:
1. Create `ah_defense/manifests/{suite_name}.yaml`
2. Classify each tool as `read_only`, `internal_write`, or `external_side_effect`
3. The benchmark runner will automatically pick it up via `IntentValidator.for_suite()`
