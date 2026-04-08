# DSPy World Proposal — Threat Analysis & Calibration Experiment

Design-time capability analysis using DSPy.

This is the **proposal layer** of the hypervisor architecture:

```
DSPy proposes the world.       ← this package
Compiler renders the world.    ← future: manifest → policy compiler
Runtime enforces the world.    ← existing: src/hypervisor.py
```

---

## Two Experiment Tracks

### Track A — Workflow Threat + Minimization Analysis

Given a workflow description (and optional tool list):

| Stage | DSPy Predictor | Output |
|---|---|---|
| 1 | `ExtractCapabilities` | inferred capability set |
| 2 | `EnumerateAttacks` | concrete attack scenarios per capability |
| 3 | `MinimizeCapabilities` | reduced set; list of removed capabilities |
| 4 | `SuggestSurrogates` | narrower replacements for risky capabilities |
| 5 | `BuildDraftManifest` | structured closed-world artifact |

### Track B — Calibration Review Assistant

Given a capability request, workflow goal, and provenance context:

| Stage | DSPy Predictor | Output |
|---|---|---|
| 1 | `ReviewCapabilityRequest` | `CalibrationVerdict` |

The verdict distinguishes:

- **direct** — capability is strictly required by the workflow
- **derived** — inferred as useful but not strictly necessary
- **adversarially_induced** — request originates from untrusted input (e.g. email body, tool output), not the workflow spec

Recommendation is one of: `approve_exact | approve_narrower | deny | require_stronger_justification`

---

## Package Structure

```
experiments/dspy_world_proposal/
  signatures.py   # DSPy Signature definitions + Pydantic output models
  modules.py      # DSPy Module pipelines (Track A + Track B)
  examples.py     # Example workflow inputs
  run_demo.py     # Terminal demo script
  README.md
```

---

## Running

```bash
cd experiments/dspy_world_proposal

# With Anthropic:
export ANTHROPIC_API_KEY=sk-ant-...
python run_demo.py

# With OpenAI:
export OPENAI_API_KEY=sk-...
python run_demo.py
```

---

## Example Workflows

**Track A, Example 1: Email Summarizer + Report Sender**
- Reads inbox, summarizes emails, sends digest to fixed recipient
- Key attack surface: inbox exfiltration, arbitrary send, prompt injection via email body

**Track A, Example 2: Repo Inspector + Test Runner + Fix Preparer**
- Reads source files, runs tests, writes patch file
- Key attack surface: shell_exec abuse, supply chain via test config, arbitrary file write

**Track B, Example 1: Adversarially Induced Filesystem Access**
- An email agent receives an email whose body requests `read_write_all_filesystem`
- The workflow spec does not require filesystem access at all
- Expected verdict: `adversarially_induced` → `deny`

---

## Connection to Compiler + Runtime

```
┌─────────────────────────────────────────────────────────┐
│  DSPy World Proposal Layer  (this package)              │
│                                                         │
│  • ExtractCapabilities  → inferred capability set       │
│  • EnumerateAttacks     → attack surface map            │
│  • MinimizeCapabilities → necessary + sufficient set    │
│  • SuggestSurrogates    → scope-reduced replacements    │
│  • BuildDraftManifest   → structured closed-world spec  │
└────────────────────┬────────────────────────────────────┘
                     │  draft_manifest (JSON)
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Manifest Compiler  (future)                            │
│                                                         │
│  • Validates manifest schema                            │
│  • Resolves surrogate definitions                       │
│  • Checks consistency (no removed cap still referenced) │
│  • Emits policy.yaml  ← deterministic, no LLM          │
└────────────────────┬────────────────────────────────────┘
                     │  policy.yaml
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Runtime Hypervisor  (src/hypervisor.py)                │
│                                                         │
│  • Evaluates agent intent against policy                │
│  • Ontological boundary: unknown tools do not exist     │
│  • Fully deterministic, no LLM calls                    │
└─────────────────────────────────────────────────────────┘
```

**Handoff point:** The `draft_manifest` dict produced by Track A is the
artifact that the compiler will consume. DSPy is responsible for proposing
it; the compiler is responsible for validating and normalizing it; the
hypervisor is responsible for enforcing it at runtime.

The proposal layer is probabilistic and iterative — it can be re-run,
compared across LMs, or optimized with DSPy's built-in optimizers.
The compiler and runtime are deterministic and do not call LLMs.
