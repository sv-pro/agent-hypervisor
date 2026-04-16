# Browser Agent Hypervisor Demo

A local-first demo showing deterministic governance of browser agent actions.

**Core claim:**
> Untrusted browser content must not directly define executable reality for the agent.

---

## What this is

Two components working together:

| Component | What it does |
|-----------|-------------|
| **Chrome Extension** | Captures page context, shows decisions, lets user trigger actions |
| **Local FastAPI Service** | Evaluates requests using deterministic world rules; never an LLM |

The extension is a **thin client**. All trust assignment, taint propagation, and
policy decisions happen in the local service — a separate process that page content
cannot reach.

---

## Project structure

```
browser-demo/
├── service/            # Python FastAPI governance service
│   ├── app/
│   │   ├── main.py         # FastAPI app entry point
│   │   ├── config.py       # Config loading (yaml + env vars)
│   │   ├── policy.py       # Deterministic rule table
│   │   ├── models.py       # Pydantic request/response types
│   │   ├── trace.py        # JSONL trace store
│   │   ├── storage.py      # In-memory event store
│   │   ├── bootstrap.py    # Bootstrap file writer
│   │   ├── world.py        # World state descriptor
│   │   ├── auth.py         # Session token auth
│   │   └── routes/         # FastAPI route handlers
│   ├── data/               # Trace and memory files (auto-created)
│   ├── config.yaml         # Service configuration
│   └── requirements.txt
├── extension/          # Chrome MV3 extension (TypeScript + React)
│   ├── src/
│   │   ├── background/     # Service worker (network client)
│   │   ├── content/        # Page capture + hidden content detection
│   │   ├── popup/          # Popup React component
│   │   ├── sidepanel/      # Side panel React component
│   │   ├── services/       # API client + bootstrap discovery
│   │   └── types/          # Shared TypeScript types
│   ├── manifest.json
│   ├── package.json
│   └── webpack.config.js
├── demo_pages/         # Local HTML demo pages
│   ├── benign.html
│   ├── suspicious.html
│   └── malicious.html
├── docs/               # Architecture and usage docs
│   ├── architecture.md
│   ├── localhost-bridge.md
│   ├── config.md
│   └── demo-scenarios.md
└── .env.example
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Chrome (or Chromium)

---

## 1 — Start the service

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

The service binds to **127.0.0.1:17841** by default.

---

## 2 — Configure the port (optional)

**Via config.yaml:**
```yaml
# browser-demo/service/config.yaml
host: 127.0.0.1
port: 19999
```

**Via environment variable:**
```bash
AH_PORT=19999 python -m app.main
```

The extension rediscovers the service on reconnect — you do not need to touch the
extension after changing the port.

---

## 3 — Build the extension

```bash
cd browser-demo/extension
npm install
npm run build     # production build → dist/
# or
npm run dev       # development build (no minification)
# or
npm run watch     # rebuild on change
```

---

## 4 — Load the extension in Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select `browser-demo/extension/dist`

The extension icon appears in the toolbar.

---

## 5 — How the extension discovers the service

The extension never hardcodes a port. On startup it:

1. Reads any previously stored service config from `chrome.storage.local`
2. Tries `GET /bootstrap` on that base URL
3. If unreachable, tries `GET http://127.0.0.1:17841/bootstrap`
4. Stores the discovered config (including session token) for authenticated calls

`/bootstrap` requires no auth token, so the extension can reach it cold.

If the service is unreachable, the popup shows a clear "disconnected" state with
instructions to start the service.

---

## 6 — Run the demo pages

```bash
cd browser-demo/demo_pages
python -m http.server 5500
```

Open in Chrome:
- `http://localhost:5500/benign.html` — ordinary content, no hidden signals
- `http://localhost:5500/suspicious.html` — hidden metadata and export hints
- `http://localhost:5500/malicious.html` — overt hostile instructions in hidden elements

For each page:
1. Open the extension popup or side panel
2. Observe trust, taint, hidden content status
3. Click actions to see decisions

---

## 7 — API overview

All endpoints except `/health` and `/bootstrap` require `X-Session-Token` header.

| Endpoint              | Method | Auth | Description                       |
|-----------------------|--------|------|-----------------------------------|
| `/health`             | GET    | No   | Service status + version          |
| `/bootstrap`          | GET    | No   | Connection info for extension     |
| `/ingest_page`        | POST   | Yes  | Submit page event; get trust/taint|
| `/evaluate`           | POST   | Yes  | Evaluate an intent; get decision  |
| `/trace/recent`       | GET    | Yes  | Last N trace entries              |
| `/world/current`      | GET    | Yes  | Active world policy config        |
| `/approval/respond`   | POST   | Yes  | Respond to an "ask" decision      |

Interactive API docs: `http://127.0.0.1:17841/docs`

---

## 8 — Sample request/response

### POST /evaluate — malicious page, save_memory

Request:
```http
POST http://127.0.0.1:17841/evaluate
X-Session-Token: demo-local-token
Content-Type: application/json

{
  "event_id": "evt-a3f9c2b1d4e5f6a7",
  "intent_type": "save_memory",
  "params": {}
}
```

Response:
```json
{
  "decision": "deny",
  "rule_hit": "RULE-SM-HIDDEN",
  "reason": "Memory write blocked: hidden content detected in page source",
  "trace_id": "tr-b2c3d4e5f6a7"
}
```

### POST /evaluate — benign page, summarize_page

Response:
```json
{
  "decision": "allow",
  "rule_hit": "RULE-SUMMARIZE-ALLOW",
  "reason": "Page summarization is a read-only operation; permitted from any source",
  "trace_id": "tr-c3d4e5f6a7b8"
}
```

---

## 9 — Intentionally not implemented

| Feature | Why out of scope |
|---------|-----------------|
| Full browser automation | This is a governance demo, not an agent |
| Arbitrary shell execution | Not needed; would be a security regression |
| Remote deployment / cloud | Local-first by design |
| Production auth stack | Session token is sufficient for local demo |
| Full policy editor | Rules are in Python code; readable and auditable |
| Heavy persistence / database | JSONL is sufficient for the demo volume |
| Multi-agent orchestration | Single agent path only |
| LLM in enforcement path | Deterministic code only — this is the whole point |
| Real memory write / export | Actions are simulated (decision only, no side effect) |

---

## Documentation

- [Architecture](docs/architecture.md) — trust/taint/decision flow
- [Localhost bridge](docs/localhost-bridge.md) — why localhost, port discovery
- [Configuration](docs/config.md) — all config options, how to change port
- [Demo scenarios](docs/demo-scenarios.md) — expected behaviour on each page
