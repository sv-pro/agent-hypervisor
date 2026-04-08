# Agent Hypervisor — Unified Repository Plan (v2)

*Refined consolidation of 5 repositories. Updated: March 2026.*

---

## Simplified Target Folder Tree

```
agent-hypervisor/
│
│  ── Root: repository-level files only ───────────────────────────────────────
│
├── README.md
├── STATUS.md
├── ROADMAP.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
│
│  ── docs/ — all concepts, architecture, research docs ───────────────────────
│
├── docs/
│   ├── CONCEPT.md                     # ← moved from root
│   ├── 12-FACTOR-AGENT.md             # ← moved from root
│   ├── FAQ.md                         # ← moved from root
│   ├── POSITIONING.md                 # ← moved from root
│   ├── THREAT_MODEL.md                # ← moved from root
│   ├── WHITEPAPER.md
│   ├── ARCHITECTURE.md                # updated to describe all submodules
│   ├── TECHNICAL_SPEC.md
│   ├── GLOSSARY.md
│   ├── REFERENCES.md
│   ├── VS_EXISTING_SOLUTIONS.md
│   ├── VULNERABILITY_CASE_STUDIES.md
│   ├── EVALUATION_FRAMEWORK.md
│   ├── HELLO_WORLD.md
│   ├── SEMANTIC_SPACE.md
│   ├── WORKAROUNDS.md
│   ├── TIMELINE.md
│   ├── concepts/
│   │   ├── perception_bounded_world.md
│   │   └── capability_rendering.md    # ← from runtime-pro/docs/
│   ├── pub/                           # article series
│   │   └── the-missing-layer/
│   └── ADR/                           # architectural decision records
│
│  ── agent_hypervisor/ — one Python package, three submodules ────────────────
│
├── agent_hypervisor/
│   ├── __init__.py
│   │
│   │  ── runtime/ — deterministic enforcement kernel ─────────────────────────
│   │  origin: safe-agent-runtime-core
│   │
│   ├── runtime/
│   │   ├── __init__.py                # public API: build_runtime(), compile_world()
│   │   ├── runtime.py                 # build_runtime() factory
│   │   ├── compile.py                 # compile_world() → CompiledPolicy
│   │   ├── ir.py                      # IRBuilder, IntentIR
│   │   ├── taint.py                   # TaintContext, TaintedValue
│   │   ├── executor.py                # Executor.execute()
│   │   ├── proxy.py                   # SafeMCPProxy
│   │   ├── channel.py                 # Channel, trust resolution
│   │   ├── models.py
│   │   ├── protocol.py
│   │   └── worker.py
│   │
│   │  ── compiler/ — World Manifest compile pipeline ─────────────────────────
│   │  origin: agent-world-compiler + agent-hypervisor/src/compiler + src/semantic
│   │
│   ├── compiler/
│   │   ├── __init__.py
│   │   ├── cli.py                     # awc CLI
│   │   ├── enforcer.py                # ALLOW / DENY_ABSENT / DENY_POLICY
│   │   ├── manifest.py                # World Manifest loader
│   │   ├── observe.py                 # trace recorder
│   │   ├── profile.py                 # derive minimal capability set
│   │   ├── render.py                  # Manifest → capability surface
│   │   ├── schema.py                  # YAML schema
│   │   ├── semantic_ir.py             # ← from src/semantic/ (semantic intermediate rep)
│   │   ├── semantic_compiler.py       # ← from src/semantic/
│   │   ├── emitter.py                 # ← from src/compiler/emitter.py
│   │   └── taint_compiler.py          # ← from src/compiler/taint_compiler.py
│   │
│   │  ── authoring/ — capability DSL and policy presets ──────────────────────
│   │  origin: safe-agent-runtime-pro
│   │
│   └── authoring/
│       ├── __init__.py
│       ├── capabilities/
│       │   ├── models.py
│       │   ├── parser.py
│       │   └── validator.py
│       ├── worlds/
│       │   ├── __init__.py            # load_world()
│       │   ├── base.py
│       │   └── email_safe.py
│       ├── integrations/
│       │   └── mcp/
│       │       └── server.py
│       └── audit/
│           └── logging.py
│
│  ── examples/ — working demonstrations ──────────────────────────────────────
│
├── examples/
│   ├── README.md
│   ├── basic/                         # simplest working demos
│   ├── compiler/                      # World Manifest scenarios: safe, unsafe, retry, zombie
│   │   └── scenarios/
│   ├── authoring/                     # capability DSL quickstart, email attack demo
│   ├── showcase/                      # end-to-end Layer 3 governance
│   └── comparisons/                   # with vs. without hypervisor
│
│  ── demos/ — interactive / presentation artifacts ──────────────────────────
│
├── demos/
│   ├── playground/                    # React/TS world visualizer
│   ├── presentation-core/
│   ├── presentation-enterprise/
│   └── presentation-faq/
│
│  ── research/ — evidence: benchmarks, traces, reports ──────────────────────
│
├── research/
│   ├── agentdojo-bench/
│   ├── benchmarks/
│   ├── reports/
│   └── traces/
│
│  ── tests/ ─────────────────────────────────────────────────────────────────
│
├── tests/
│   ├── runtime/
│   ├── compiler/
│   └── authoring/
│
│  ── archive/ — superseded by status, not by origin ─────────────────────────
│  Nothing here is imported or maintained. Pure historical record.
│
└── archive/
    ├── README.md                      # explains what was archived and when
    ├── superseded-enforcement/        # runtime-pro material superseded by runtime/ + authoring/
    │   └── ...                        # safe-agent-runtime-pro: worlds, audit, integrations
    │                                  # that did not get promoted to authoring/
    └── superseded-compiler-poc/       # awc poc modules superseded by compiler/
        ├── observe/recorder.py        # superseded by compiler/observe.py
        ├── compiler/compile_manifest.py  # superseded by compiler/manifest.py
        ├── compiler/profiler.py       # superseded by compiler/profile.py
        ├── compiler/render_tools.py   # superseded by compiler/render.py
        ├── policy/engine.py           # superseded by runtime/compile.py
        └── notebooks/                 # jupyter experiment — worth reading, not running
            └── pipeline_walkthrough.ipynb
```

---

## Self-Critique: Too Complicated / Just Right / Too Flat

### What is too complicated (v1 mistakes, now fixed)

**`src/` wrapper dir with 4 peer subdirs.** The original plan had `src/hypervisor/`, `src/runtime/`, `src/compiler/`, `src/authoring/` as four peers inside `src/`. This mimics the old repo structure inside the new repo — it preserves the boundary, not the concept. One Python package with submodules is cleaner and idiomatic.

**`lab/` as a named category.** "Lab" implies an active workspace. In practice it was going to be a garbage collector: everything too messy for main, too recent for archive. Without a strict admission policy it fills up. Abolished — material is either promoted to canonical or goes to archive.

**Having CONCEPT.md, 12-FACTOR-AGENT.md, FAQ.md, POSITIONING.md, THREAT_MODEL.md at root level.** These are conceptual documents. They belong in `docs/`. Root is for repository plumbing, not for reading.

**Archive organized by origin repo (`runtime-pro/`, `old-poc/`).** Genealogy is not useful for a reader who just found the archive directory. Status-by-content (`superseded-enforcement/`, `superseded-compiler-poc/`) tells you why something was archived, not where it came from.

**Fake monorepo via `src/` fragmentation.** The previous structure implied three independent packages. Using submodules of one package `agent_hypervisor/` is the correct signal: these are not independent deployables, they are internal architecture layers.

### What is just right (kept)

**`docs/` absorbs all conceptual material.** Clean separation: root = repo plumbing, docs/ = everything you read.

**`research/` as a distinct top-level.** Benchmarks, traces, and reports are evidence artifacts. They are read differently from implementation or documentation. Separating them avoids contaminating either.

**`examples/` grouped by scenario domain**, not origin repo. `examples/compiler/` contains compiler scenarios regardless of which repo they came from.

**`archive/` exists and is non-empty from day one.** An archive with entries signals that the repo takes deprecation seriously. An empty archive signals that nothing was ever cleaned up.

**Promotion of `src/semantic/` into `compiler/`.** The `semantic_ir.py`, `semantic_compiler.py` files are implementation support for the compiler pipeline — they belong in `compiler/`, not as a peer to it.

### What could become too flat (risk to watch)

**`agent_hypervisor/compiler/` might grow too wide.** The compiler has multiple concerns: manifest loading, enforcement, rendering, profiling, semantic IR, taint compilation. If it grows beyond ~10 modules, consider splitting `compiler/engine/` vs `compiler/pipeline/` — but do not do this preemptively.

**`examples/` grouping.** Three top-level scenario groups (`compiler/`, `authoring/`, `showcase/`) is right for now. If authoring examples multiply they may need sub-grouping. Hold until needed.

---

## v1 Migration Plan — First Cleanup Pass

Optimized for correctness and speed. Each step is independently committable.

### Step 1 — Clean the root (30 min)

Move these root-level docs into `docs/`:
- `CONCEPT.md` → `docs/CONCEPT.md`
- `12-FACTOR-AGENT.md` → `docs/12-FACTOR-AGENT.md`
- `FAQ.md` → `docs/FAQ.md`
- `POSITIONING.md` → `docs/POSITIONING.md`
- `THREAT_MODEL.md` → `docs/THREAT_MODEL.md`

Update README.md internal links.  
**Commit: `chore: move conceptual docs into docs/`**

### Step 2 — Create the package skeleton (15 min)

Create `agent_hypervisor/` with empty `__init__.py` files for `runtime/`, `compiler/`, `authoring/`.  
Move existing `src/` content into `agent_hypervisor/`:
- `src/agent_hypervisor/` contents → `agent_hypervisor/`
- `src/boundary/` → flatten into `agent_hypervisor/` (it contains `intent_proposal.py`, `semantic_event.py` — these belong in the core package)
- Update `pyproject.toml` package name

**Commit: `refactor: create agent_hypervisor package structure`**

### Step 3 — Promote runtime kernel (1 hr)

Copy `safe-agent-runtime-core/runtime/` → `agent_hypervisor/runtime/`.  
Copy `safe-agent-runtime-core/tests/` → `tests/runtime/`.  
Run tests. Fix import paths (`from runtime import ...` → `from agent_hypervisor.runtime import ...`).  
**Commit: `feat: add agent_hypervisor.runtime (from safe-agent-runtime-core)`**

### Step 4 — Promote compiler (1.5 hr)

Copy `agent-world-compiler/agent_world_compiler/` → `agent_hypervisor/compiler/`.  
Merge `src/compiler/emitter.py`, `src/compiler/taint_compiler.py` → `agent_hypervisor/compiler/`.  
Move `src/semantic/*.py` worth keeping → `agent_hypervisor/compiler/` (evaluate each file).  
Copy `agent-world-compiler/tests/` → `tests/compiler/`.  
Copy `agent-world-compiler/scenarios/` → `examples/compiler/scenarios/`.  
Run tests. Fix imports.  
**Commit: `feat: add agent_hypervisor.compiler (from agent-world-compiler)`**

### Step 5 — Promote authoring layer (1 hr)

Copy `safe-agent-runtime-pro/safe_agent_runtime_pro/` → `agent_hypervisor/authoring/`.  
Move `safe-agent-runtime-pro/docs/capability-rendering.md` → `docs/concepts/capability_rendering.md`.  
Copy `safe-agent-runtime-pro/examples/` → `examples/authoring/`.  
Copy `safe-agent-runtime-pro/tests/` → `tests/authoring/`.  
Run tests. Fix imports.  
**Commit: `feat: add agent_hypervisor.authoring (from safe-agent-runtime-pro)`**

### Step 6 — Organize research and demos (30 min)

Move:
- `benchmarks/` → `research/benchmarks/`
- `agentdojo-bench/` → `research/agentdojo-bench/`
- `reports/` → `research/reports/`
- `traces/` → `research/traces/`
- `presentation-core/` → `demos/presentation-core/`
- `presentation-enterprise/` → `demos/presentation-enterprise/`
- `presentation-faq/` → `demos/presentation-faq/`
- `playground/` → `demos/playground/`

**Commit: `chore: organize research/ and demos/`**

### Step 7 — Archive superseded material (45 min)

**Evaluate compiler-poc module by module:**

| poc module | verdict | action |
|------------|---------|--------|
| `compiler/compile_manifest.py` | superseded by `compiler/manifest.py` | archive |
| `compiler/profiler.py` | superseded by `compiler/profile.py` | archive |
| `compiler/render_tools.py` | superseded by `compiler/render.py` | archive |
| `observe/recorder.py` | superseded by `compiler/observe.py` | archive |
| `policy/engine.py` | superseded by `runtime/compile.py` | archive |
| `policy/evaluate.py` | superseded by `runtime/ir.py` | archive |
| `policy/taint.py` | superseded by `runtime/taint.py` | archive |
| `notebooks/pipeline_walkthrough.ipynb` | unique — historical walkthrough | archive/notebooks |

Move identified superseded material to `archive/superseded-compiler-poc/`.  
Move superseded runtime-pro content to `archive/superseded-enforcement/`.  
Write `archive/README.md` explaining what is there and why.  
**Commit: `chore: archive superseded poc and enforcement material`**

### Step 8 — Update ARCHITECTURE.md (1 hr)

Rewrite `docs/ARCHITECTURE.md` to describe:
- `agent_hypervisor.runtime` — enforcement kernel
- `agent_hypervisor.compiler` — manifest pipeline
- `agent_hypervisor.authoring` — capability DSL

Update all inter-doc cross-references to new paths.  
**Commit: `docs: update ARCHITECTURE.md to reflect unified package structure`**

### Step 9 — Archive the old repos (external, last)

After all tests pass in `agent-hypervisor`:
- Add pointer README to each archived repo: `agent-world-compiler`, `safe-agent-runtime-core`, `safe-agent-runtime-pro`, `agent-world-compiler-poc`
- Archive each repo on GitHub

---

## Non-goals of v1

These are correct in principle but not for the first cleanup pass:

- Writing `docs/components/runtime-core.md`, `compiler.md`, `authoring.md` — do this after the code is in place
- Updating `docs/GLOSSARY.md` with new terms — defer to after ARCHITECTURE.md is updated
- Adding `ahc validate`, `ahc simulate` — these are roadmap items, not consolidation items
- Reorganizing `docs/pub/` summit material — low priority; do not create work for the sake of completeness
