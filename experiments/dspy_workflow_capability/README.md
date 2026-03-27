# dspy_workflow_capability

Design-time assistant for capability set analysis and calibration review.

## What this does

Given a workflow description, this experiment:

1. **Extracts** the full set of capabilities implied by the workflow (including implicit ones).
2. **Enumerates** adversarial attack scenarios against that capability set.
3. **Minimizes** the capability set to the smallest sufficient subset, guided by attack analysis.
4. **Proposes surrogates** — narrower, constrained forms of each kept capability.
5. **Synthesizes a draft manifest** in the `world_manifest.yaml` schema for human review.

A second, independent flow:

6. **Reviews capability requests** — given a proposed capability and the workflow it claims to support, decides `allow / flag / deny` and flags adversarially-induced requests.

## What this does NOT do

- **No runtime enforcement.** All output is for human review. Nothing compiled here is executed.
- **No automatic compilation.** The draft manifest must be reviewed and committed manually.
- **No policy decisions.** This layer proposes; the human reviewer and the compiler decide.
- **No training data generation.** Examples in `examples.py` are authored, not generated.

## Relation to the broader system

```
[This experiment]
    ↓ draft manifest (human-reviewed)
[compiler/semantic_manifest.py]   ← SemanticCompiler consumes reviewed manifest
    ↓ compiled policy
[runtime/compile.py]              ← CompiledPolicy, frozen at startup
    ↓
[runtime/runtime.py]              ← Enforcement at call time, no LLM involved
```

The output of this experiment feeds into `compiler/semantic_manifest.py`.
The compiler is deterministic; this experiment is the only LLM-assisted step.

## Core principles preserved

- Closed per-workflow capability set (no open-ended tool access)
- Minimal sufficient capabilities (MinimizeCapabilities step)
- Narrow surrogates preferred over broad tools (SuggestSurrogates step)
- No blind expansion (ReviewCapabilityRequest rejects unanticipated requests)
- Provenance tracked (request_context field in ReviewCapabilityRequest)
- Adversarially-induced requests flagged (adversarial_risk field)
- Proposals only — human gate before any compilation

## File structure

```
experiments/dspy_workflow_capability/
  __init__.py      — package marker
  signatures.py    — DSPy signatures (contracts, no logic)
  modules.py       — Module wiring (skeleton, no prompt engineering)
  examples.py      — Authored example I/O for two workflows + two calibration cases
  run_demo.py      — Demo runner (Phase 1: no optimization)
  README.md        — This file
```

## Phase 2 (not yet)

- DSPy optimization (MIPROv2 or BootstrapFewShot) over authored examples
- Structured output enforcement (typed dspy.OutputField validators)
- Evaluation metrics: precision of dropped capabilities, attack coverage
- Integration test against `compiler/semantic_manifest.py`
