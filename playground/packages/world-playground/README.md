# Agent World Playground

> **The problem is not only behavior. The problem is the world.**

An interactive browser-based demo that visually shows the difference between
*behavior filtering* (permissions) and *world rendering* (ontology-based
action-space design) for AI agent safety.

---

## What this demonstrates

Most agent safety approaches work by blocking bad actions after they are proposed.
This playground shows a different abstraction: **render the agent's world** so that
dangerous actions never enter the vocabulary in the first place.

The key moment: type `git rm -rf .` and the system responds not with `DENIED` but with:

```
NO SUCH ACTION IN THIS WORLD
```

Governance was never reached. The action had no capability to map to.

---

## Four scenarios

| # | Scenario | Model | Key result |
|---|----------|-------|------------|
| 1 | Bash + Permissions | Permission model | Destructive action is expressible; governance is the only gate |
| 2 | Rendered Capability World | World rendering | `git rm` absent from actor's world; governance never reached |
| 3 | Email Ontology | Ontology narrowing | Arbitrary recipient not in vocabulary; problem solved at design time |
| 4 | Tainted Input | Taint + rendering | Untrusted email cannot drive external sends; two independent safety properties |

---

## Why "not expressible" instead of "denied"

A `DENIED` result means:
- The action was formed
- It reached governance
- Governance rejected it

This is the weakest guarantee: governance must be correct, always, for every action.

A "not expressible" result means:
- The action cannot be formed in this world
- No governance rule is needed
- The property holds regardless of governance correctness

This is the difference between a lock on a door that exists, and a world where
the door was never built.

---

## Install & run

```bash
# From repo root
cd playground/packages/world-playground
npm install
npm run dev
```

Open: http://localhost:5174

Or from the playground monorepo root:

```bash
cd playground
npm install
npm run dev:world-playground
```

---

## Architecture

```
src/
  data/
    types.ts          — TypeScript interfaces
    scenarios.ts      — Four built-in scenario definitions
  components/
    RawRealityPanel   — Incoming input + raw tool space
    SemanticEventPanel — Typed event viewer (YAML-style)
    RenderedWorldPanel — Actor-visible capabilities vs. hidden tools
    IntentPanel        — Agent intent → capability mapping
    GovernancePanel    — Verdict + layer trace
    InsightPanel       — Per-scenario explanation
    LayerModel         — Expandable 4-layer conceptual model
    ScenarioSelector   — Tab-style scenario switcher
  App.tsx             — State management + pipeline layout
  index.css           — Tailwind v4 theme tokens
```

No backend. No LLM. All scenario logic is handcrafted, deterministic mappings.
The point is architecture, not NLP.

---

## Tech stack

- React 19
- Vite 6
- Tailwind CSS v4
- Framer Motion 11
- TypeScript 5

---

## The four layers

| Layer | Name | Role |
|-------|------|------|
| L0 | Execution Physics | OS, network, file system |
| L1 | Base Ontology | Full vocabulary of typed actions |
| L2 | Dynamic World Rendering | Context-specific capability projection |
| L3 | Execution Governance | Allow / ask / deny |

Layer 2 is decisive. It determines what the actor can even propose.
Layer 3 governs what survives Layer 2.

---

## Key phrases in the UI

- *Permissions try to stop bad actions.*
- *Rendering removes them from the action space.*
- *The safest action is the one the actor cannot even propose.*
- *An action outside the ontology cannot be proposed.*
- *Security is action-space design.*
- *No such action in this world.*
- *Governance never reached.*

---

## Next iteration ideas

- Live input parsing: detect intent from typed text in real time
- Custom scenario builder: let users define their own ontology
- Animated diff mode: show raw → rendered transition as dissolve
- Taint graph: visualize how taint propagates through a multi-step plan
- Export as shareable link with scenario state encoded in URL
