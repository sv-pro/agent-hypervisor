# Agent Hypervisor — Full-Stack Demo

Interactive demo of reality virtualization for AI agents.

## Quick Start

```bash
npm install
npm run dev
```

Opens: http://localhost:5173

## What this demonstrates

A compromised AI agent always tries to exfiltrate data.
A malicious skill from an external marketplace contains a hidden `curl` command.

**MODE 1** (no hypervisor): attack succeeds silently.
**MODE 2** (with hypervisor): ontologically impossible.
Not because blocked — because the action does not exist.

Based on: Cisco AI Threat Research / OpenClaw incident, Feb 2026.

## Architecture

```
Reality → [Hypervisor] → Agent
```

The hypervisor:
1. Virtualizes input (canonicalize, assign trust, compute taint)
2. Collapses capabilities when data is tainted
3. Evaluates intents against deterministic physics laws

Trust is determined by channel, not content.
Tainted data collapses capabilities to zero.
The agent cannot formulate intent for actions that do not exist.

## Scenarios

| | Title | Insight |
|---|---|---|
| **A** | ZombieAgent / OpenClaw Case | canonicalization ≠ trust |
| **B** | Trust = Channel | capabilities = physics of this world |
| **C** | MCP as Virtual Device | tools are devices, not possessions |
| **D** | Simulate, not Execute | simulate = a different world, not a block |

## Key files

```
packages/hypervisor/src/policy.ts  — policy engine (pure functions)
packages/agent/src/compromised.ts  — intentionally compromised mock agent
packages/server/src/scenarios.ts   — 4 attack scenarios
packages/dashboard/src/            — React frontend
```

## Tech stack

- TypeScript (strict mode)
- Fastify + WebSocket (backend)
- React + Vite + Tailwind CSS (frontend)
- npm workspaces (monorepo)
- No external AI APIs — fully offline
