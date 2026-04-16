# Architecture

## Core claim

> Untrusted browser content must not directly define executable reality for the agent.

This demo makes that claim legible by separating two things that are often conflated:

- **What the page says** (untrusted, tainted, from the web)
- **What the agent is allowed to do** (decided by a local, deterministic governance kernel)

---

## Two components

### 1. Chrome Extension (thin client)

The extension is a **client**, not a security kernel. Its job is:

- Capture visible text from the current page
- Detect hidden content (CSS-hidden elements, aria-hidden text, zero-width characters, HTML comments)
- Send a structured `PageSnapshot` to the local service
- Display the service's response (trust, taint, decision, trace)
- Let the user trigger intent actions via buttons

The extension has **no policy logic**. It cannot decide what is allowed. It can only report and display.

### 2. Local Hypervisor Service (governance kernel)

The service is a **FastAPI application running on localhost**. Its job is:

- Receive page events from the extension
- Assign trust based on source type
- Propagate taint deterministically
- Evaluate user-triggered intents against a world policy
- Return decisions to the extension
- Log a trace of every evaluation

All policy logic is **deterministic Python code** — no LLM, no probabilistic filter, no embedding comparison.

---

## Data flow

```
Browser tab
  │
  ├─ content.ts (content script)
  │     Captures page: text, title, URL, hidden content detection
  │     Sends → background.ts
  │
  ├─ background.ts (service worker)
  │     Calls POST /ingest_page → local service
  │     Receives: event_id, trust, taint, available_actions
  │     Stores state in chrome.storage.local
  │
  ├─ popup.html / sidepanel.html (React UI)
  │     Reads state from background (via messages)
  │     User clicks action → sends TRIGGER_ACTION to background
  │     Background calls POST /evaluate → local service
  │     Decision displayed in UI
  │
Local Hypervisor Service (127.0.0.1:17841)
  │
  ├─ POST /ingest_page
  │     Assigns trust (web_page → untrusted)
  │     Assigns taint (untrusted or hidden_content → tainted)
  │     Returns event_id, trust, taint, available_actions
  │
  ├─ POST /evaluate
  │     Looks up stored event
  │     Applies deterministic rule table
  │     Returns decision, rule_hit, reason
  │     Appends trace entry to JSONL log
  │
  └─ GET /trace/recent
        Returns last N trace entries for display
```

---

## Trust model

| Source type         | Assigned trust |
|---------------------|----------------|
| `web_page`          | untrusted      |
| `extension_ui`      | trusted        |
| `manual_user_input` | trusted        |
| (anything else)     | untrusted      |

Trust is assigned at ingestion time and cannot be changed by page content.

---

## Taint model

Taint is a **monotonic boolean**. Once tainted, always tainted.

A page event is tainted if:
- Its trust is `untrusted`, **or**
- `hidden_content_detected` is `true`

Pages with hidden instructions are always tainted regardless of URL or declared source.

---

## Policy rules (ordered, first match wins)

| Intent              | Condition                 | Decision |
|---------------------|---------------------------|----------|
| `save_memory`       | hidden content detected   | deny     |
| `save_memory`       | untrusted source          | ask      |
| `export_summary`    | tainted content           | deny     |
| `summarize_page`    | any                       | allow    |
| `extract_links`     | any                       | allow    |
| `extract_action_items` | any                    | allow    |
| `save_memory`       | trusted source            | allow    |
| `export_summary`    | clean (non-tainted)       | allow    |
| (default)           | any                       | deny     |

Rules are evaluated in declaration order. No LLM is involved. Identical inputs always produce identical outputs.

---

## What this is NOT

- Not a full browser automation system
- Not a cloud service
- Not a production security product
- Not prompt-injection research (though it demonstrates the threat)
- Not an AI agent that can take autonomous actions

This is a local demo showing the architecture of deterministic governance.
