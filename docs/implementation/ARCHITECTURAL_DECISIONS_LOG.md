# Architectural Decisions Log

Running log of implementation decisions made during the AH MCP Gateway build.

---

## ADL-001 — New module: `hypervisor/mcp_gateway/` (not a rewrite of existing gateway)

**Date**: 2026-04-09  
**Decision**: Create a new `mcp_gateway/` module alongside the existing `hypervisor/gateway/` rather than modifying `gateway_server.py`.  
**Why**: The existing gateway is a working PoC that exercises provenance firewall logic. Modifying it risks breaking that logic and conflating two concerns (custom REST API vs. MCP protocol). Additive approach is safer and cleaner.  
**Alternatives rejected**:
- Modify `gateway_server.py` to add MCP endpoints → rejected (breaks separation, risks regression)
- Replace `gateway_server.py` → rejected (destroys working provenance PoC)
**Consequences**: Two gateway implementations coexist. The new MCP gateway reuses registry and policy engine from the old one.

---

## ADL-002 — JSON-RPC 2.0 over HTTP POST (not SSE)

**Date**: 2026-04-09  
**Decision**: Implement the MCP transport as HTTP POST with JSON-RPC 2.0 request/response body. No SSE streaming.  
**Why**: SSE (Server-Sent Events) adds significant complexity for the initial version. POST+JSON-RPC is sufficient for `tools/list` and `tools/call` and is compatible with the MCP spec's Streamable HTTP transport for these request types.  
**Alternatives rejected**:
- Full SSE transport → deferred (too complex for Phase 1)
- stdio transport → not suitable for a remote gateway
**Consequences**: Initial version is not suitable for streaming tool outputs. SSE can be added later without changing the enforcement architecture.

---

## ADL-003 — `tools/list` is world rendering, not discovery

**Date**: 2026-04-09  
**Decision**: `tools/list` returns only tools declared in the WorldManifest AND registered in the ToolRegistry. Undeclared tools are absent — they do not exist in this world.  
**Why**: Ontological absence is more robust than runtime rejection. A tool that is never listed cannot be accidentally called. This matches the core AH principle: remove possibilities at compile time rather than filter at runtime.  
**Alternatives rejected**:
- List all registered tools and filter on call → rejected (tool is visible, creating a foothold for prompt injection attacks that enumerate the tool surface)
- List all tools with a "forbidden" marker → rejected (forbidden ≠ absent)
**Consequences**: The manifest drives discovery. Changing the manifest changes the visible world. Adapter registration is separate from ontological inclusion.

---

## ADL-004 — `manifest.tool_names()` for declaration check, not `manifest.allows(tool, args)`

**Date**: 2026-04-09  
**Decision**: In `ToolCallEnforcer.enforce()`, the "is this tool declared at all?" check uses `tool_name not in manifest.tool_names()` rather than `not manifest.allows(tool_name, args)`.  
**Why**: `manifest.allows(tool, args)` combines two separate concerns: (1) is the tool declared, and (2) do the call arguments satisfy the constraints. Merging them gives the wrong error code when a declared tool is called with constraint-violating args (we get "not declared" instead of "constraint violated"). The fix separates declaration from constraint checking.  
**Alternatives rejected**:
- Use `manifest.allows()` for all checks → rejected (conflates declaration and constraint checks)
**Consequences**: `ToolCallEnforcer` has four explicit pipeline stages: declare-check → registry-check → policy-check → constraint-check. Each produces a distinct matched_rule identifier.

---

## ADL-005 — Fail-closed startup: manifest load failure raises

**Date**: 2026-04-09  
**Decision**: `SessionWorldResolver.__init__()` calls `load_manifest()` which raises on failure. The gateway does not start if the manifest cannot be loaded.  
**Why**: A gateway that starts without a manifest would either serve no tools (acceptable) or serve all tools (catastrophic). Rather than guess, we make the failure explicit and visible at startup. Operators know immediately if the manifest file is missing or invalid.  
**Alternatives rejected**:
- Default to empty manifest on load failure → deferred (acceptable for a future "maintenance mode" but not a safe default)
- Default to permissive/all-tools manifest → rejected (security regression)
**Consequences**: Deployment requires a valid manifest file. This is documented in the demo and README.

---

## ADL-006 — Provenance as metadata-only in Phase 5

**Date**: 2026-04-09  
**Decision**: Phase 5 provenance hooks capture source metadata (`InvocationProvenance`) and attach it to `EnforcementDecision`, but do not wire it to the existing `TaintContext` / `IRBuilder` system in `runtime/`.  
**Why**: Full taint integration requires understanding the runtime's process-boundary invariant (enforcement in main process, execution in subprocess). Wiring provenance to runtime taint would require understanding that boundary deeply and risks breaking the canonical taint invariant. The metadata-only approach provides audit value without the risk.  
**Alternatives rejected**:
- Full taint integration in Phase 5 → deferred (too complex, risk of breaking runtime invariant)
- No provenance at all → rejected (loses audit trail)
**Consequences**: Provenance metadata is available in `EnforcementDecision.provenance` but not used for enforcement decisions. A future phase can wire `trust_level` → `TaintState` when the runtime boundary is fully understood.

---

## ADL-007 — Reuse existing ToolRegistry, not a new adapter system

**Date**: 2026-04-09  
**Decision**: The MCP gateway reuses `build_default_registry()` from `hypervisor/gateway/tool_registry.py` for adapter dispatch.  
**Why**: The existing registry is well-defined, has working adapters, and already matches the tool names we care about. Inventing a parallel adapter system would create unnecessary duplication.  
**Alternatives rejected**:
- New adapter protocol for MCP → rejected (duplication with no benefit at this stage)
**Consequences**: MCP-visible tools are constrained to tools that have adapters in the existing registry. New tools require adapter registration in the existing registry before they can appear in any world manifest.
