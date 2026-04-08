# Agent Hypervisor — Unified Repository Structure (v2)

*Simplified target tree. One package, clean root, semantic archive.*

---

```
agent-hypervisor/
│
│  ROOT: repository-level files only ─────────────────────────────────────────
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
│  docs/ — everything you read ────────────────────────────────────────────────
│
├── docs/
│   ├── CONCEPT.md                     # ← moved from root
│   ├── 12-FACTOR-AGENT.md             # ← moved from root
│   ├── FAQ.md                         # ← moved from root
│   ├── POSITIONING.md                 # ← moved from root
│   ├── THREAT_MODEL.md                # ← moved from root
│   ├── WHITEPAPER.md
│   ├── ARCHITECTURE.md
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
│   │   └── capability_rendering.md       ← from safe-agent-runtime-pro/docs/
│   ├── pub/
│   │   └── the-missing-layer/
│   └── ADR/
│
│  agent_hypervisor/ — one package, three submodules ─────────────────────────
│
├── agent_hypervisor/
│   ├── __init__.py
│   │
│   ├── runtime/              # enforcement kernel (from safe-agent-runtime-core)
│   │   ├── __init__.py       #   public API: build_runtime(), compile_world(), ...
│   │   ├── runtime.py        #   build_runtime() entry point
│   │   ├── compile.py        #   compile_world() → CompiledPolicy
│   │   ├── ir.py             #   IRBuilder, IntentIR
│   │   ├── taint.py          #   TaintContext, TaintedValue
│   │   ├── executor.py       #   Executor.execute()
│   │   ├── proxy.py          #   SafeMCPProxy
│   │   ├── channel.py        #   Channel, trust resolution
│   │   ├── models.py
│   │   ├── protocol.py
│   │   └── worker.py
│   │
│   ├── compiler/             # World Manifest pipeline (from agent-world-compiler
│   │   ├── __init__.py       #   + src/semantic/ + src/compiler/)
│   │   ├── cli.py            #   awc CLI
│   │   ├── enforcer.py       #   ALLOW / DENY_ABSENT / DENY_POLICY
│   │   ├── manifest.py       #   World Manifest loader
│   │   ├── observe.py        #   trace recorder
│   │   ├── profile.py        #   derive minimal capability set
│   │   ├── render.py         #   Manifest → capability surface
│   │   ├── schema.py         #   YAML schema
│   │   ├── semantic_ir.py    #   semantic intermediate representation
│   │   ├── semantic_compiler.py
│   │   ├── emitter.py        #   artifact emitter
│   │   └── taint_compiler.py #   taint → compiled state machine
│   │
│   └── authoring/            # capability DSL + policy presets
│       ├── __init__.py       #   (from safe-agent-runtime-pro)
│       ├── capabilities/
│       │   ├── models.py
│       │   ├── parser.py
│       │   └── validator.py
│       ├── worlds/
│       │   ├── __init__.py   #   load_world()
│       │   ├── base.py
│       │   └── email_safe.py
│       ├── integrations/mcp/
│       │   └── server.py
│       └── audit/
│           └── logging.py
│
│  examples/ — working demonstrations ────────────────────────────────────────
│
├── examples/
│   ├── README.md
│   ├── basic/                # smallest working demos
│   ├── compiler/             # World Manifest: safe, unsafe, retry, zombie
│   │   └── scenarios/
│   ├── authoring/            # capability DSL quickstart, email attack demo
│   ├── showcase/             # end-to-end Layer 3 governance
│   └── comparisons/          # with vs. without hypervisor
│
│  demos/ — presentations and interactive artifacts ──────────────────────────
│
├── demos/
│   ├── playground/           # React/TS world virtualization visualizer
│   ├── presentation-core/
│   ├── presentation-enterprise/
│   └── presentation-faq/
│
│  research/ — evidence ──────────────────────────────────────────────────────
│
├── research/
│   ├── agentdojo-bench/
│   ├── benchmarks/
│   ├── reports/
│   └── traces/
│
│  tests/ ────────────────────────────────────────────────────────────────────
│
├── tests/
│   ├── runtime/
│   ├── compiler/
│   └── authoring/
│
│  archive/ — archived by status, not by origin ──────────────────────────────
│  Nothing here is imported. Pure historical record.
│
└── archive/
    ├── README.md
    ├── superseded-compiler-poc/    # old awc poc — superseded module for module
    │   ├── observe/recorder.py     #   ← now: compiler/observe.py
    │   ├── compiler/               #   ← now: compiler/{manifest,profile,render}.py
    │   ├── policy/                 #   ← now: runtime/{compile,ir,taint}.py
    │   └── notebooks/              #   pipeline walkthrough — readable, not runnable
    └── superseded-enforcement/     # runtime-pro material not promoted to authoring/
        └── ...
```

---

## Placement rationale

| Decision | Why |
|----------|-----|
| Root has ≤9 files | Root is navigated first. Conceptual docs buried in the root reward no one. |
| One package `agent_hypervisor/` | These are not independent deployables. Using submodules says: they are architecture layers, not products. |
| `compiler/` absorbs `src/semantic/` | The semantic IR and semantic compiler are implementation support for the compiler pipeline. They have no standalone identity. |
| No `lab/` directory | "Lab" has no admission policy, so it fills up. Material is either ready to promote or ready to archive — there is no third state. |
| `archive/` named by what was superseded | A reader of `archive/superseded-compiler-poc/` knows why it's there. A reader of `archive/agent-world-compiler-poc/` does not. |
| summit docs stay in `docs/pub/` | They are drafts of published material, not junk. They belong with the publication series. |

---

*See [CONSOLIDATION_PLAN.md](CONSOLIDATION_PLAN.md) for migration steps.*  
*See [STATUS.md](STATUS.md) for component maturity.*
