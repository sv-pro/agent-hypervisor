# Repository Structure

Canonical layout for the Agent Hypervisor repository.

---

## Core

| Path | Purpose |
|------|---------|
| `src/agent_hypervisor/` | Core hypervisor: runtime kernel, compiler, authoring DSL, policy engine |
| `src/agent_hypervisor/runtime/` | Layer 3: IRBuilder, taint, provenance, executor, proxy |
| `src/agent_hypervisor/compiler/` | Layer 1: World Manifest schema, loader, enforcer, CLI |
| `src/agent_hypervisor/authoring/` | Layer 2: Capability DSL and policy presets |
| `src/agent_hypervisor/hypervisor/` | Hypervisor PoC, gateway, policy engine |
| `src/agent_hypervisor/economic/` | Budget and cost enforcement |

## Manifests and scenarios

| Path | Purpose |
|------|---------|
| `manifests/` | World Manifest YAML files |
| `scenarios/` | Scenario definitions for demos and tests |

## Browser demo system

> `browser-demo/` is the browser-based demo system.
> `browser-demo/extension/` is the service-connected Chrome extension client.
> `browser-demo/extension-standalone/` is the standalone (in-extension policy) Chrome extension.
> There is no second parallel browser demo root.

| Path | Purpose |
|------|---------|
| `browser-demo/` | Complete browser-based demo system |
| `browser-demo/extension/` | Chrome MV3 thin client — delegates policy to the local service |
| `browser-demo/extension-standalone/` | Chrome MV3 standalone — in-extension policy via compiled World Manifests |
| `browser-demo/service/` | Python FastAPI governance service (local bridge) |
| `browser-demo/demo_pages/` | Full-featured HTML demo pages (benign, suspicious, malicious) |
| `browser-demo/docs/` | Browser demo documentation (both extensions + service) |

### Design principle

The browser demo system demonstrates two complementary architectural claims:

1. **Process-boundary isolation** (`extension/` + `service/`): policy decisions run in a
   separate process that web content cannot reach.
2. **Compiled-manifest governance** (`extension-standalone/`): YAML World Manifests are
   compiled at build time into deterministic rules that cannot be influenced by page content.

Both extensions are governed implementations; they make different points about *where* the
governance kernel should live.

## Examples and research

| Path | Purpose |
|------|---------|
| `examples/` | Runnable demonstrations of core hypervisor features |
| `research/` | Benchmarks, AgentDojo integration, research reports |
| `experiments/` | Exploratory research (DSPy, etc.) |

## Documentation

| Path | Purpose |
|------|---------|
| `docs/concept/` | Core concepts and overview |
| `docs/architecture/` | Whitepaper, threat model, ADRs |
| `docs/pub/` | Published article series |
| `docs/adr/` | Architecture Decision Records |

## Do not modify

| Path | Why |
|------|-----|
| `archive/` | Historical experimental code |
| `lab/` | Archived PoC notebooks |
| `browser-extension-demo/` | Migrated to `browser-demo/extension-standalone/` |

---

## Deprecated

`browser-extension-demo/` — this directory previously housed the standalone Chrome
extension demo. It has been consolidated into `browser-demo/extension-standalone/`.
Only a deprecation `README.md` remains. Do not add code there.
