# Browser Agent Hypervisor Demo

A local-first demo showing deterministic governance of browser agent actions.

**Core claim:**
> Untrusted browser content must not directly define executable reality for the agent.

---

## What this is

The `browser-demo/` directory is the complete browser-based demo system. It contains
two complementary extension implementations, a governance service, and shared demo pages.

---

## Two extension approaches

Both demonstrate the same core claim from different architectural angles.

### 1 — Service-connected extension (`extension/`)

The extension is a **thin client**. All trust assignment, taint propagation, and policy
decisions happen in the local Python FastAPI service — a separate process that page content
cannot reach.

```
web content → extension (thin client) → local service (kernel)
(untrusted)    (reports + displays)     (decides, traces, enforces)
```

This demonstrates **process-boundary isolation**: the governance kernel is architecturally
unreachable from the content it evaluates.

### 2 — Standalone extension (`extension-standalone/`)

All policy evaluation runs **inside the extension** using deterministic rules compiled from
YAML World Manifests. No backend required. Also shows naive vs governed mode side-by-side.

This demonstrates **compiled-manifest governance**: a YAML World Manifest is compiled at
build time into deterministic TypeScript rules that cannot be influenced by page content.

See [`docs/localhost-bridge.md`](docs/localhost-bridge.md) for the architectural reasoning
behind each approach.

---

## Project structure

```
browser-demo/
├── extension/              # Chrome MV3 thin client (service-connected)
│   ├── src/
│   │   ├── background/     # Service worker (HTTP client to local service)
│   │   ├── content/        # Page capture + hidden content detection
│   │   ├── popup/          # Popup React component
│   │   ├── sidepanel/      # Side panel React component
│   │   ├── services/       # API client + bootstrap discovery
│   │   └── types/          # Shared TypeScript types
│   ├── manifest.json
│   ├── package.json        # Webpack
│   └── webpack.config.js
├── extension-standalone/   # Chrome MV3 standalone (in-extension policy, Vite)
│   ├── src/
│   │   ├── agents/         # NaiveAgent, GovernedAgent, AgentProvider
│   │   ├── compare/        # World comparison engine
│   │   ├── core/           # Domain types: approval, intent, policy, taint, trace
│   │   ├── demo/           # Demo page detector, scenario helpers
│   │   ├── extension/      # Background, content, popup, sidepanel entry points
│   │   ├── state/          # Approval queue
│   │   ├── ui/             # React components (sidepanel, trace, world editor)
│   │   └── world/          # World Manifest compiler, parser, validator
│   ├── public/
│   │   ├── manifest.json
│   │   └── demo/           # Minimal demo HTML stubs for Vite dev server
│   ├── package.json        # Vite
│   └── vite.config.ts
├── service/                # Python FastAPI governance service
│   ├── app/
│   │   ├── main.py         # Entry point
│   │   ├── config.py       # Config loading
│   │   ├── policy.py       # Deterministic rule table
│   │   ├── models.py       # Pydantic types
│   │   ├── trace.py        # JSONL trace store
│   │   ├── storage.py      # In-memory event store
│   │   ├── bootstrap.py    # Bootstrap file writer
│   │   ├── world.py        # World state descriptor
│   │   ├── auth.py         # Session token auth
│   │   └── routes/         # FastAPI route handlers
│   ├── data/               # Trace and memory files (auto-created)
│   ├── config.yaml
│   └── requirements.txt
├── demo_pages/             # Full-featured HTML demo pages
│   ├── benign.html         # Ordinary content, no hidden signals
│   ├── suspicious.html     # Hidden metadata + export hints
│   └── malicious.html      # Overt hostile instructions in hidden elements
├── docs/                   # Architecture and feature documentation
│   ├── architecture.md
│   ├── localhost-bridge.md
│   ├── config.md
│   ├── demo-scenarios.md
│   ├── phase2.md           # extension-standalone feature roadmap
│   ├── approval_flow.md
│   ├── trace_model.md
│   ├── world-schema.md
│   ├── world-authoring.md
│   └── ...
└── .env.example
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Chrome (or Chromium)

---

## Running the service-connected demo

### 1 — Start the service

```bash
cd browser-demo/service
pip install -r requirements.txt
python -m app.main
```

Expected output:
```
[hypervisor] bootstrap written → /home/you/.agent-hypervisor/bootstrap.json
[hypervisor] service ready — http://127.0.0.1:17841  (token: demo-local-token)
INFO:     Uvicorn running on http://127.0.0.1:17841
```

### 2 — Build the extension

```bash
cd browser-demo/extension
npm install
npm run build     # production build → dist/
```

### 3 — Load in Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `browser-demo/extension/dist`

### 4 — Run demo pages

```bash
cd browser-demo/demo_pages
python -m http.server 5500
```

Open in Chrome:
- `http://localhost:5500/benign.html`
- `http://localhost:5500/suspicious.html`
- `http://localhost:5500/malicious.html`

---

## Running the standalone extension demo

### 1 — Build the extension

```bash
cd browser-demo/extension-standalone
npm install
npm run build     # → dist/
```

### 2 — Load in Chrome

1. `chrome://extensions` → Enable Developer mode
2. Load unpacked → select `browser-demo/extension-standalone/dist`

### 3 — Run demo pages

The standalone extension uses minimal stubs served by the Vite dev server:

```bash
cd browser-demo/extension-standalone
npm run dev       # serves at http://localhost:5173
```

Open:
- `http://localhost:5173/demo/benign.html`
- `http://localhost:5173/demo/suspicious.html`
- `http://localhost:5173/demo/malicious.html`

Or use the richer shared demo pages (served separately):

```bash
cd browser-demo/demo_pages
python -m http.server 5500
```

---

## Service API overview

All endpoints except `/health` and `/bootstrap` require `X-Session-Token` header.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | No | Service status + version |
| `/bootstrap` | GET | No | Connection info for extension |
| `/ingest_page` | POST | Yes | Submit page event; get trust/taint |
| `/evaluate` | POST | Yes | Evaluate an intent; get decision |
| `/trace/recent` | GET | Yes | Last N trace entries |
| `/world/current` | GET | Yes | Active world policy config |
| `/approval/respond` | POST | Yes | Respond to an "ask" decision |

Interactive API docs: `http://127.0.0.1:17841/docs`

---

## Documentation

| Doc | Topic |
|-----|-------|
| [architecture.md](docs/architecture.md) | Trust/taint/decision flow |
| [localhost-bridge.md](docs/localhost-bridge.md) | Why a local service; port discovery |
| [config.md](docs/config.md) | Service configuration options |
| [demo-scenarios.md](docs/demo-scenarios.md) | Expected behaviour on each page |
| [phase2.md](docs/phase2.md) | Standalone extension feature roadmap |
| [approval_flow.md](docs/approval_flow.md) | ASK/approval lifecycle |
| [trace_model.md](docs/trace_model.md) | Decision trace schema |
| [world-schema.md](docs/world-schema.md) | World Manifest YAML schema |
| [world-authoring.md](docs/world-authoring.md) | How to write manifests |

---

## Intentionally not implemented

| Feature | Why out of scope |
|---|---|
| Full browser automation | This is a governance demo, not an agent |
| Arbitrary shell execution | Not needed; would be a security regression |
| Remote deployment / cloud | Local-first by design |
| Production auth stack | Session token is sufficient for local demo |
| LLM in enforcement path | Deterministic code only — this is the whole point |
| Real memory write / export | Actions are simulated (decision only, no side effect) |
