# Repo Consolidation Audit: browser-demo + browser-extension-demo

**Date:** 2026-04-16  
**Branch:** `claude/consolidate-browser-demo-jLrhL`  
**Decision:** Consolidate into `browser-demo/` as canonical root.

---

## 1. Current contents of each directory

### `browser-demo/` (49 files) — added in PR #107

**Purpose:** Local-first demo demonstrating the architectural claim that *policy decisions must not run in the same trust boundary as the content being evaluated.* The extension is a thin HTTP client; the Python FastAPI service is the governance kernel in a separate process.

| Subdirectory | Contents |
|---|---|
| `extension/` | Chrome MV3 thin client (TypeScript + React + Webpack); talks to local service via HTTP |
| `service/` | Python FastAPI governance service; deterministic rule table, taint/trace, approval routes |
| `demo_pages/` | Full-featured HTML demo pages (benign, suspicious, malicious) — ~2.8–3.8 KB each |
| `docs/` | architecture.md, config.md, demo-scenarios.md, localhost-bridge.md |
| `.env.example` | Environment variable template |
| `README.md` | Full setup guide (256 lines) |

### `browser-extension-demo/` (69 files) — added in PRs #102–104

**Purpose:** In-extension governance demo comparing naive vs governed agent modes. Policy evaluation runs inside the extension using deterministic rules compiled from YAML World Manifests. No backend required.

| Subdirectory | Contents |
|---|---|
| `src/agents/` | AgentProvider interface, NaiveAgent, GovernedAgent |
| `src/compare/` | World comparison engine, action surface, scenarios (Phase 4) |
| `src/core/` | Core domain types: approval, intent, memory, policy, taint, trace, world, simulation |
| `src/demo/` | Demo page detector, scenario definitions |
| `src/extension/` | Chrome MV3 extension structure (background, content, popup, sidepanel) |
| `src/state/` | Approval queue state |
| `src/ui/` | React UI: sidepanel sections, trace viewer, world editor, compare views |
| `src/world/` | YAML World Manifest compiler, parser, validator, diff, presets, version store |
| `public/manifest.json` | Chrome extension manifest |
| `public/demo/` | Minimal demo HTML pages (400–700 B each, for vite dev server) |
| `docs/` | 11 docs: phase2, approval_flow, trace_model, world-schema, world-authoring, etc. |
| `package.json` | Vite + React + TypeScript + js-yaml |
| `README.md` | Brief overview (87 lines) |

---

## 2. Overlaps

### Exact filename conflicts

| File | browser-demo | browser-extension-demo | Resolution |
|---|---|---|---|
| `manifest.json` | `extension/manifest.json` — thin client; `host_permissions: ["http://127.0.0.1:*/*"]` | `public/manifest.json` — standalone; `host_permissions: ["<all_urls>"]` | **Keep both** — architecturally distinct, placed in separate subdirs |
| `benign.html` | `demo_pages/benign.html` — full-featured, 2789 B | `public/demo/benign.html` — minimal stub, 401 B | **Keep both** — serve different purposes |
| `suspicious.html` | `demo_pages/suspicious.html` — 3342 B | `public/demo/suspicious.html` — 583 B | **Keep both** |
| `malicious.html` | `demo_pages/malicious.html` — 3871 B | `public/demo/malicious.html` — 740 B | **Keep both** |
| `README.md` | Full setup guide | Brief overview | **Merge** browser-extension-demo content into browser-demo/README.md |

### Conceptual overlaps (different paths, related purpose)

| Concept | browser-demo | browser-extension-demo |
|---|---|---|
| Extension background worker | `extension/src/background/background.ts` | `src/extension/background/index.ts` |
| Content script | `extension/src/content/content.ts` | `src/extension/content/index.ts` |
| Popup | `extension/src/popup/Popup.tsx` | `src/extension/popup/main.tsx` |
| Side panel | `extension/src/sidepanel/SidePanel.tsx` | `src/extension/sidepanel/main.tsx` |
| Policy logic | `service/app/policy.py` | `src/core/policy.ts` + world compiler |
| Trace model | `service/app/trace.py` | `src/core/trace.ts` |

These are **not duplicates** — the thin-client extension delegates to the service; the standalone extension evaluates policy internally. They implement different halves of different architectural claims.

### Internal reference conflict

`browser-demo/docs/localhost-bridge.md` line 6 refers to `browser-extension-demo` by name. This reference will be updated to `browser-demo/extension-standalone/` after migration.

---

## 3. Proposed merge mapping

### Extension-standalone code (self-contained, world-manifest-based)

```
browser-extension-demo/src/          → browser-demo/extension-standalone/src/
browser-extension-demo/public/       → browser-demo/extension-standalone/public/
browser-extension-demo/package.json  → browser-demo/extension-standalone/package.json
browser-extension-demo/vite.config.ts → browser-demo/extension-standalone/vite.config.ts
browser-extension-demo/tsconfig.json → browser-demo/extension-standalone/tsconfig.json
browser-extension-demo/package-lock.json → browser-demo/extension-standalone/package-lock.json
```

### Docs (no filename conflicts)

```
browser-extension-demo/docs/phase2.md              → browser-demo/docs/phase2.md
browser-extension-demo/docs/approval_flow.md       → browser-demo/docs/approval_flow.md
browser-extension-demo/docs/trace_model.md         → browser-demo/docs/trace_model.md
browser-extension-demo/docs/world-schema.md        → browser-demo/docs/world-schema.md
browser-extension-demo/docs/world-authoring.md     → browser-demo/docs/world-authoring.md
browser-extension-demo/docs/world-versioning.md    → browser-demo/docs/world-versioning.md
browser-extension-demo/docs/world-comparison-model.md → browser-demo/docs/world-comparison-model.md
browser-extension-demo/docs/world-test-panel.md    → browser-demo/docs/world-test-panel.md
browser-extension-demo/docs/comparative-playground.md → browser-demo/docs/comparative-playground.md
browser-extension-demo/docs/exported-comparison-format.md → browser-demo/docs/exported-comparison-format.md
browser-extension-demo/docs/scenario-replay.md     → browser-demo/docs/scenario-replay.md
```

### README

```
browser-extension-demo/README.md → content merged into browser-demo/README.md
                                    + deprecation notice left in browser-extension-demo/README.md
```

---

## 4. Files requiring manual review

**None.** No unresolvable conflicts were found. The two extension codebases do not share code and serve architecturally distinct purposes. Both can coexist cleanly under `browser-demo/`.

---

## Summary of decisions

1. **Canonical root:** `browser-demo/`
2. **Thin-client extension** (`browser-demo/extension/`) — unchanged; pairs with the Python service.
3. **Standalone extension** (`browser-demo/extension-standalone/`) — receives all of `browser-extension-demo/` content; uses Vite; self-contained.
4. **Demo pages** — `browser-demo/demo_pages/` keeps the richer full-featured pages; `extension-standalone/public/demo/` keeps the minimal stubs for the Vite dev workflow.
5. **Docs** — all 11 `browser-extension-demo/docs/` files move to `browser-demo/docs/`; no filename collisions.
6. **Deprecation** — `browser-extension-demo/` will contain only a `README.md` pointing to the new canonical location.
