# Browser Agent Hypervisor — Standalone Extension

This Chrome MV3 extension demonstrates in-extension deterministic governance comparing:

- **Naive Agent mode** — weak mediation, ingests raw content directly
- **Governed Agent mode** — deterministic policy mediation with trust + taint + trace

**Architectural claim:**
> Untrusted web content must not become executable reality for the agent.

Unlike `browser-demo/extension/` (which delegates all policy decisions to the local Python service), this extension evaluates policy **inside the extension** using deterministic rules compiled from YAML World Manifests. There is no backend required.

---

## Build

```bash
cd browser-demo/extension-standalone
npm install
npm run build     # → dist/
```

Load in Chrome:
1. `chrome://extensions` → Enable Developer mode
2. Load unpacked → select `browser-demo/extension-standalone/dist`

---

## Dev server

```bash
npm run dev       # starts Vite dev server with HMR
```

Demo pages are served at:
- `http://localhost:5173/demo/benign.html`
- `http://localhost:5173/demo/suspicious.html`
- `http://localhost:5173/demo/malicious.html`

Richer standalone demo pages are also available in `browser-demo/demo_pages/` (serve with `python -m http.server 5500`).

---

## Source layout

```
extension-standalone/
├── src/
│   ├── agents/       # NaiveAgent, GovernedAgent, AgentProvider interface
│   ├── compare/      # World comparison engine (Phase 4)
│   ├── core/         # Domain types: approval, intent, policy, taint, trace, simulation
│   ├── demo/         # Demo page detector, scenario helpers
│   ├── extension/    # Chrome MV3 structure: background, content, popup, sidepanel
│   ├── state/        # Approval queue state
│   ├── ui/           # React components: sidepanel, trace viewer, world editor, compare
│   └── world/        # World Manifest compiler, parser, validator, diff, presets
├── public/
│   ├── manifest.json # Chrome extension manifest
│   └── demo/         # Minimal demo HTML stubs for dev server
├── package.json      # Vite + React + TypeScript + js-yaml
├── vite.config.ts
└── tsconfig.json
```

---

## Documentation

All docs live in `browser-demo/docs/`:

| Doc | Topic |
|-----|-------|
| `phase2.md` | Feature roadmap: approval flow, simulation, world authoring |
| `approval_flow.md` | ASK/approval lifecycle |
| `trace_model.md` | Decision trace schema |
| `world-schema.md` | World Manifest YAML schema |
| `world-authoring.md` | How to write manifests |
| `world-versioning.md` | Version history model |
| `world-comparison-model.md` | World comparison semantics |
| `world-test-panel.md` | In-UI world testing |
| `comparative-playground.md` | Side-by-side world comparison UI |
| `exported-comparison-format.md` | Export format specification |
| `scenario-replay.md` | Scenario replay system |

---

## Relation to the service-connected extension

`browser-demo/extension/` is a **thin client** that delegates all policy evaluation to the
local Python FastAPI service (`browser-demo/service/`). It demonstrates the process-boundary
isolation claim.

This extension (`extension-standalone/`) runs policy **in-browser** using compiled World
Manifests. It demonstrates that deterministic YAML-compiled rules are sufficient for
governance without a backend process.

Both approaches are valid; they make different architectural points. See
`browser-demo/docs/localhost-bridge.md` for the reasoning behind the service-separated approach.
