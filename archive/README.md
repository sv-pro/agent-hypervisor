# archive/

This directory contains materials that are superseded, obsolete, or were replaced by better implementations. Nothing here is imported or maintained. It is preserved for historical reference and auditability.

---

## experimental-poc/

**What:** Modules from `agent-world-compiler-poc` — the original proof-of-concept compiler, written before the production `agent_hypervisor.compiler` existed.

**Why archived:** Each module has been superseded:

| poc module | superseded by |
|------------|---------------|
| `compile_manifest.py` | `agent_hypervisor/compiler/manifest.py` |
| `profiler.py` | `agent_hypervisor/compiler/profile.py` |
| `render_tools.py` | `agent_hypervisor/compiler/render.py` |
| `observe/recorder.py` | `agent_hypervisor/compiler/observe.py` |
| `policy/engine.py` | `agent_hypervisor/runtime/compile.py` |
| `policy/evaluate.py` | `agent_hypervisor/runtime/ir.py` |
| `policy/taint.py` | `agent_hypervisor/runtime/taint.py` |

The `notebooks/` subdirectory contains `pipeline_walkthrough.ipynb` —
a Jupyter notebook that walks through the original design. It is historically
useful for understanding the evolution of the enforcement model. It is **not
runnable** against the current codebase.

---

## superseded-docs/

**What:** Documentation that was either replaced by the new docs structure or was
redundant internal tooling (Claude prompts, task lists, scratch files).

Notable files:
- `CLAUDE_CODE_PROMPT*.md` — internal AI coding session prompts, not architecture
- `VERIFICATION_PLAN.md` — superseded by the test suite
- `PROJECT_TASKS.md` — superseded by the ROADMAP

---

## obsolete-schemas/

**What:** Schema files that have been superseded by a newer version or replaced by
code-level schema definitions.

---

*Last updated: March 2026*
