# Browser Agent Hypervisor Demo Extension (MVP)

This Chrome MV3 extension is a focused demo that compares:

- **Naive Agent mode** (plausible baseline, weak mediation)
- **Governed Agent mode** (deterministic policy mediation with trust + taint + trace)

It exists to demonstrate one architectural claim:

> Untrusted web content must not become executable reality for the agent.

## What this extension does

### Utility mode (useful assistant)
- Summarize current page
- Extract links
- Extract action items
- Save note to memory
- Export summary (simulated side effect)

### Attack lab mode (legible threat demo)
Use local demo pages (`public/demo/*.html`) to trigger:
- hidden instruction injection
- memory poisoning attempts
- tool/external action pivot attempts

## Architecture overview

Core flow:
1. **Content script** captures page snapshot (visible text, raw text, hidden signals).
2. Snapshot becomes a **Semantic Event** (`source_type`, trust, taint, content hash, etc).
3. User action maps to a typed **Intent Proposal**.
4. In governed mode, deterministic **Policy Layer** decides `allow | deny | ask | simulate`.
5. Governed actions emit a **Decision Trace** with rule hit and timestamp.
6. Memory entries carry **trust/taint/provenance** metadata.

## Naive vs Governed behavior

- **Naive**
  - Ingests broader raw content path.
  - Saves memory directly.
  - Simulates export without policy mediation.

- **Governed**
  - Treats `web_page` as untrusted and tainted by default.
  - Applies deterministic policy for every intent.
  - Blocks tainted export, asks before memory write from untrusted page.
  - Logs decision trace records.

## Run locally

```bash
cd browser-extension-demo
npm install
npm run build
```

Then in Chrome:
1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `browser-extension-demo/dist`

## Run demo pages

Serve demo files locally:

```bash
cd browser-extension-demo/public
python -m http.server 5500
```

Open:
- `http://localhost:5500/demo/benign.html`
- `http://localhost:5500/demo/suspicious.html`
- `http://localhost:5500/demo/malicious.html`

Then open the extension popup/side panel and run actions in both modes.

## What is intentionally not implemented

- No autonomous browsing/actions beyond bounded demo intents.
- No production backend, auth, or enterprise persistence.
- No full prompt-injection detection research system.
- No real external export connector (export is simulated output).
- No LLM in enforcement path (policy is deterministic code).
