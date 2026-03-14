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

The AH defense operates as two `BasePipelineElement` subclasses inside `ToolsExecutionLoop`:

```
ToolsExecutionLoop([
    ToolsExecutor,          # Execute tools → add tool result messages
    AHInputSanitizer,       # ① Canonicalize outputs, mark taint
    LLM,                    # Propose next tool calls
    AHTaintGuard,           # ② Validate calls against taint + manifest
])
```

### AHInputSanitizer (pre-LLM)
- Strips known injection patterns (`IMPORTANT!!! Ignore...`, `[[SYSTEM:...]]`, zero-width chars)
- Wraps outputs with trust metadata (`[AH|SOURCE:tool|TRUST:untrusted]`)
- Marks all tool results as tainted in shared `TaintState`

### AHTaintGuard (post-LLM)
- Reads LLM's proposed tool calls
- For each call: checks `tool_type` in World Manifest
- **TaintContainmentLaw**: if `taint_context=True` AND `tool_type=external_side_effect` → **BLOCK**
- Blocked calls are removed; LLM receives error feedback

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

## Expected Results Table

When fully benchmarked, the output will resemble:

| Defense | Suite | Utility (clean) | Utility (attack) | ASR |
|---------|-------|-----------------|-----------------|-----|
| none | workspace | ~85% | ~85% | ~60% |
| spotlighting | workspace | ~83% | ~80% | ~40% |
| agent_hypervisor | workspace | ~80% | ~78% | ~15% |
| CaMeL (paper) | workspace | 77% | 77% | 0% |

> AH targets: >80% utility preservation + significant ASR reduction vs. baseline.
> CaMeL's 0% ASR comes from provable taint tracking at value granularity with dual-LLM.
> AH's approach achieves message-level taint containment without any LLM on the security path.

## Benchmark Versions

The default benchmark version is `v1.2.2`. AgentDojo supports:
- `v1` — original benchmark
- `v1.2.2` — current recommended (includes more injection tasks)

## Extending

To add a new suite manifest:
1. Create `ah_defense/manifests/{suite_name}.yaml`
2. Classify each tool as `read_only`, `internal_write`, or `external_side_effect`
3. The benchmark runner will automatically pick it up via `IntentValidator.for_suite()`
