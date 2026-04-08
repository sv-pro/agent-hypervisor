# Verification Plan

*Post-implementation review checklist. Work through this after all issues are implemented.*

Each entry maps to a GitHub issue and states the acceptance criteria from PROJECT_TASKS.md plus specific verification actions.

---

## How to use this document

For each task:
1. Run the listed commands / checks.
2. Mark `[x]` when satisfied.
3. Note any gaps or follow-up issues found.

---

## M1 Foundation — Documentation

### #1 README v2
- [ ] `README.md` renders correctly on GitHub (headings, table, code block).
- [ ] All document links resolve (WHITEPAPER, CONCEPT, 12-FACTOR-AGENT, FAQ, ROADMAP, POSITIONING, THREAT MODEL, ARCHITECTURE, GLOSSARY).
- [ ] Quickstart commands (`git clone`, `pip install -e .`, `python examples/basic/01_simple_demo.py`) still work.

### #2 CONCEPT.md v2
- [ ] §8 Architectural Invariants present with I-1 through I-7.
- [ ] §9 Relationship to 12-Factor Agent table present.
- [ ] No bare URLs (MD034). Run: `markdownlint CONCEPT.md` or grep for raw http.
- [ ] Cross-references (§8, ARCHITECTURE.md, WHITEPAPER.md) resolve.

### #3 THREAT_MODEL.md
- [ ] Six trust channels documented with correct trust levels.
- [ ] Five in-scope threats: prompt injection, tainted egress, tool abuse, MCP injection, memory poisoning.
- [ ] Six out-of-scope constraints documented.
- [ ] Section 7 bounded security claim present.

### #4 ARCHITECTURE.md (docs/)
- [ ] Layer numbering matches CONCEPT.md (L1=Input Boundary, L5=Execution Boundary).
- [ ] Module map table present with current status per layer.
- [ ] "Not yet implemented" table with issue numbers.
- [ ] Conformance test pattern present.

### #5 ARCHITECTURE.md (docs/) — was same PR as #4, verify complete.

### #6 FAQ.md
- [ ] Answers: "Is this a guardrail?", "Is this a sandbox?", "Is this an MCP proxy?", "Is this a policy engine?".
- [ ] Semantic gap question answered with honest limitation.
- [ ] HITL design-time rationale explained.
- [ ] "What does the architecture actually guarantee?" section present.

### #7 GLOSSARY.md
- [ ] All 8 required terms present: semantic event, intent proposal, World Manifest, capability matrix, taint propagation, provenance, escalation condition, virtualized device.
- [ ] Each definition is self-contained (no undefined cross-terms).
- [ ] Footer references ARCHITECTURE.md (not TECHNICAL_SPEC.md).

### #8 ROADMAP.md
- [ ] Design→Compile→Deploy→Learn→Redesign cycle diagram present.
- [ ] Three stages table: PoC, Executable Proof, Beta Product.
- [ ] M2–M5 milestone tables link to issue numbers.
- [ ] "What Done Looks Like" section present for all three stages.

### #9 POSITIONING.md
- [ ] Four things clearly separated: architecture thesis, reference implementation, research claims, mini-product.
- [ ] Explicit list of what the project does NOT claim.
- [ ] Current objective stated (PoC + focused product surface, not universal platform).
- [ ] Alignment table with all major docs.

---

## M2 Core Engine — Compiler + Runtime

### #10 World Manifest schema v1
- [ ] `manifests/schema.yaml` has all 8 sections: metadata, actions, trust_channels, capability_matrix, taint_rules, escalation_conditions, provenance_schema, budgets.
- [ ] All fields are documented inline.
- [ ] Three example manifests present: email-safe-assistant, mcp-gateway-demo, browser-agent-demo.
- [ ] Each example covers at least one of: prompt injection, tainted egress, trusted workflow.
- [ ] Verify: `ahc build manifests/examples/email-safe-assistant.yaml` succeeds.
- [ ] Verify: `ahc build manifests/examples/mcp-gateway-demo.yaml` succeeds.
- [ ] Verify: `ahc build manifests/examples/browser-agent-demo.yaml` succeeds.

### #11 Compiler CLI (`ahc build`)
- [ ] `ahc build <manifest> --output <dir>` works.
- [ ] Produces 8 artifacts: policy_table, capability_matrix, taint_rules, taint_state_machine, escalation_table, provenance_schema, action_schemas, manifest_meta.
- [ ] Same manifest → identical artifacts on two consecutive runs (determinism).
  ```bash
  ahc build manifests/examples/email-safe-assistant.yaml -o /tmp/run1 -q
  ahc build manifests/examples/email-safe-assistant.yaml -o /tmp/run2 -q
  diff -r /tmp/run1 /tmp/run2  # must be empty
  ```
- [ ] `manifest_meta.json` contains `content_hash`.
- [ ] Invalid manifest exits non-zero with descriptive error.
- [ ] `pytest tests/test_compiler.py` — all pass.

### #12 Taint rule compiler
- [ ] `taint_state_machine.json` present in each compiled output.
- [ ] Has 4 keys: `taint_order`, `transition_table`, `containment_rules`, `sanitization_index`.
- [ ] `taint_order` = `["UNTRUSTED", "SEMI_TRUSTED", "TRUSTED"]`.
- [ ] Conflict detection: conflicting rules log to `conflicts` list, first rule wins.
- [ ] `pytest tests/test_taint_compiler.py` — all pass.

### #13 Semantic Event model
- [ ] `SemanticEvent` is a frozen dataclass (immutable).
- [ ] `Provenance` is a frozen dataclass (immutable).
- [ ] `SemanticEventFactory` has: `from_user`, `from_email`, `from_web`, `from_file`, `from_mcp`, `from_agent`.
- [ ] Email/web/agent channels always produce `taint=True`.
- [ ] User channel always produces `taint=False`, `trust_level=TRUSTED`.
- [ ] Known injection patterns stripped from UNTRUSTED payloads.
- [ ] `pytest tests/test_semantic_event.py` — all pass.

### #14 Intent Proposal API
- [ ] `IntentProposal` is a frozen dataclass.
- [ ] `IntentProposalBuilder` propagates `taint` and `trust_level` from the triggering `SemanticEvent`.
- [ ] Agent cannot upgrade trust level.
- [ ] Agent cannot clear taint.
- [ ] `source_event_id` links proposal to its SemanticEvent (provenance chain).
- [ ] `with_elevated_taint()` available for conservative mixed-data propagation.
- [ ] `pytest tests/test_intent_proposal.py` — all pass.

### #15 Deterministic policy engine
- [ ] `PolicyEngine.from_compiled_dir(path)` loads all artifacts.
- [ ] `evaluate(proposal)` returns `PolicyDecision` with verdict + reason_chain.
- [ ] 5-check evaluation order: ontology → capability → taint → escalation → budget.
- [ ] Four verdicts available: `allow`, `deny`, `require_approval`, `simulate`.
- [ ] Same proposal → same verdict on two independent engine instances.
- [ ] `pytest tests/test_policy_engine.py` — all pass.

### #16 Provenance graph
- [ ] `ProvenanceGraph.record_event/proposal/decision/execution` all work.
- [ ] Edges created: `agent_formed_intent`, `policy_evaluated`, `executed`.
- [ ] `trace(id)` returns ancestor chain from proposal back to SemanticEvent.
- [ ] `save(path)` writes valid JSONL; `load(path)` reconstructs graph.
- [ ] `summary()` returns node counts, tainted count, verdict distribution.
- [ ] `pytest tests/test_policy_engine.py::TestProvenanceGraph` — all pass.

### #17 Determinism and ontology tests
- [ ] All 7 invariants covered by automated tests (I-1 through I-7).
- [ ] Conformance pattern tested without mocking the agent:
  - `untrusted_input → denied`
  - `tainted_object → export_blocked`
  - `trusted_input → allowed`
  - `action_not_in_ontology → denied`
- [ ] `pytest tests/test_invariants.py` — all pass.

---

## M3 Tool Boundary

### #18 MCP proxy skeleton
- [ ] `MCPGateway.from_compiled_dir(dir, registry, session_id)` loads without error.
- [ ] `gateway.call(proposal)` always returns `(output | None, GatewayTrace)`.
- [ ] `GatewayTrace` has all required fields: `trace_id`, `proposal_id`, `tool`, `args`, `trust_level`, `taint`, `timestamp`, `outcome`, `denial_reason`, `output_event_id`.
- [ ] Denied calls produce `trace.outcome != "executed"` with non-empty `denial_reason`.
- [ ] `gateway.traces()` accumulates all calls; `gateway.clear_traces()` resets.
- [ ] `pytest tests/test_gateway.py::TestMCPProxySkeleton` — all pass.

### #19 Tools as virtualized devices
- [ ] Tool not in manifest → `outcome == "not_in_world"`.
- [ ] Denial message says "does not exist" and does NOT contain "forbidden".
- [ ] Tool present in mcp-gateway manifest but not email manifest: email gateway gets `not_in_world`, mcp gateway does not.
- [ ] `get_available_tools(TRUSTED)` returns all tools in manifest.
- [ ] `get_available_tools(UNTRUSTED)` returns subset (no external_write tools visible).
- [ ] Dangerous tools (exec, rm, bash, shell, curl) not in manifest → all `not_in_world`.
- [ ] `pytest tests/test_gateway.py::TestVirtualizedDevices` — all pass.

### #20 Tool descriptor schema
- [ ] Missing required arg → `outcome == "schema_error"` before execution.
- [ ] `schema_error` denial reason mentions the missing field name.
- [ ] All required args present → schema check passes (outcome is not `schema_error`).
- [ ] Extra/unknown args are NOT blocked (permissive extra-fields policy).
- [ ] `pytest tests/test_gateway.py::TestToolDescriptorSchema` — all pass.

### #21 Capability matrix enforcement
- [ ] `UNTRUSTED` trust level cannot invoke `external_write` tools → `outcome == "capability_denied"`.
- [ ] `capability_denied` denial reason mentions `"external_write"`.
- [ ] `TRUSTED` can invoke `list_inbox` → `outcome == "executed"`.
- [ ] `SEMI_TRUSTED` with tainted data → blocked (either `capability_denied` or `taint_blocked`).
- [ ] `pytest tests/test_gateway.py::TestCapabilityMatrixEnforcement` — all pass.

### #22 Taint-aware egress control
- [ ] Tainted `send_email` (from email source) → blocked (`taint_blocked` or `capability_denied`).
- [ ] Blocked denial reason is non-empty (explains which law fired).
- [ ] Tainted `list_inbox` → NOT `taint_blocked` (read-only tools not blocked by taint).
- [ ] Clean (untainted) `send_email` from user → taint gate passes; outcome is NOT `taint_blocked`.
- [ ] Web-tainted `mcp_write_file` → blocked (`taint_blocked` or `capability_denied`).
- [ ] `pytest tests/test_gateway.py::TestTaintAwareEgressControl` — all pass.

### #23 Provenance for tool outputs
- [ ] Successful call returns a `SemanticEvent` instance (not raw dict).
- [ ] `output.source` contains the tool name.
- [ ] `output.trust_level` matches the tool's `output_trust` field in manifest.
- [ ] `output.provenance.source_channel` starts with `"MCP:"`.
- [ ] `output.provenance.event_id` is non-empty.
- [ ] `trace.output_event_id == output.provenance.event_id`.
- [ ] `read_email` output is `taint=True` (UNTRUSTED output_trust).
- [ ] MCP output event can feed next `IntentProposalBuilder`; taint propagates.
- [ ] `pytest tests/test_gateway.py::TestProvenanceForToolOutputs` — all pass.
- [ ] `pytest tests/test_gateway.py` — **all 32 pass**.

---

## M4 Proof

### #24 Interactive demo v1
- [ ] `python examples/basic/02_hypervisor_demo.py` runs without error.
- [ ] Scenario A shows email injection stripped at Layer 1, denied at Layer 4 capability check.
- [ ] Scenario B shows poisoned tool output propagating taint to downstream proposal.
- [ ] Scenario C shows legitimate TRUSTED workflow: list_inbox→allow, send_email→require_approval.
- [ ] Every step prints channel, trust_level, taint, sanitized_payload, verdict, and reason chain.

### #25 Demo: poisoned tool output
- [ ] Scenario B of the demo demonstrates poisoned tool output (MCP → downstream write).
- [ ] MCP list_directory output is labeled SEMI_TRUSTED with taint=True.
- [ ] Downstream mcp_write_file proposal inherits taint from the output event.
- [ ] Policy engine denies the write at capability check (SEMI_TRUSTED cannot external_write).
- [ ] Outcome is reproducible across runs (deterministic).

### #26 Benchmark scenario taxonomy
- [ ] `benchmarks/scenarios/` has subdirs: `attack/`, `safe/`, `ambiguous/`.
- [ ] At least 4 attack scenarios: prompt injection, web injection, poisoned tool output, ontology escape.
- [ ] At least 3 safe scenarios: list_inbox, read_email, mcp_list_directory.
- [ ] At least 2 ambiguous scenarios: send_email (trusted, irreversible), mcp_run_code.
- [ ] Each fixture has: `scenario_id`, `class`, `manifest`, `channel`, `intent`, `expected_outcome`.
- [ ] `benchmarks/scenarios/README.md` documents the format and coverage targets.
- [ ] `python benchmarks/runner.py` loads all 9 scenarios without error.

### #28 Baseline runner
- [ ] `python benchmarks/runner.py` exits 0; hypervisor 9/9 correct.
- [ ] Runner saves JSONL trace to `benchmarks/traces/run-<timestamp>.jsonl`.
- [ ] `--mode baseline` / `--mode hypervisor` / `--mode both` all work.
- [ ] Baseline correctly executes attacks (demonstrates value of boundary).

### #29 Metrics and report v1
- [ ] `python benchmarks/metrics.py --output benchmarks/reports/report-v1.md` exits 0.
- [ ] `benchmarks/reports/report-v1.md` contains all 7 metrics tables.
- [ ] Attack containment rate = 100%, false deny rate = 0%, task completion = 100%.
- [ ] Latency overhead reported in milliseconds.

### #30 Trace replay and walkthrough
- [ ] `python benchmarks/replay.py` exits 0; reports "PASSED — all outcomes stable".
- [ ] `python benchmarks/replay.py --walkthrough` prints per-scenario reason chain.
- [ ] All 9 hypervisor scenarios replay with identical outcome (determinism verified).

---

## M5 Beta Product

### #31 Docker local stack
- [ ] `Dockerfile` builds successfully (`docker build .`).
- [ ] `docker compose up demo` runs the three-scenario demo without error.
- [ ] `docker compose up benchmarks` runs runner + metrics + replay and prints report.
- [ ] `docker-compose.yml` has `demo` and `benchmarks` services.
- [ ] Manifests and benchmarks directories are mounted as volumes.

### #32 Web UI
- [ ] Deferred: no web UI implemented. Docker compose + CLI tools are the primary interface.
- [ ] `docker compose run demo bash` gives an interactive shell for exploration.
- [ ] Note: full web UI (tabs: manifests, decisions, traces, provenance) is a future milestone.

### #33 Quickstart and walkthrough
- [ ] `docs/QUICKSTART.md` exists and covers all 6 steps.
- [ ] Step 1 (install) works: `pip install -e .` + `ahc build` produces 8 artifacts.
- [ ] Step 2 (demo) works: `python examples/basic/02_hypervisor_demo.py` shows all 3 scenarios.
- [ ] Step 3 (change manifest + rebuild) walkthrough is accurate and demonstrates physics change.
- [ ] Step 4 (benchmark + report) commands all exit 0.
- [ ] Step 5 (replay) commands exit 0 with "PASSED — all outcomes stable".
- [ ] Step 6 (Docker) commands work.
- [ ] Total time from clone to first benchmark result ≤ 10 minutes.

### #34 Content-to-proof packaging
- [ ] `docs/PROOF_PACKAGE.md` exists.
- [ ] Every claim in the argument maps to a specific test or artifact.
- [ ] Claim → artifact table has ≥ 11 rows covering all major invariants.
- [ ] Executable proof section has copy-pasteable commands that all work.
- [ ] Document map table covers all major docs.
- [ ] Non-claims section is explicit about scope limits.

---

## Cross-cutting checks (run when all milestones are complete)

- [ ] `pytest tests/` — 215+ tests, all pass.
- [ ] Full pipeline smoke test:
  ```bash
  ahc build manifests/examples/email-safe-assistant.yaml -o /tmp/smoke -q
  python examples/basic/02_hypervisor_demo.py
  python benchmarks/runner.py
  python benchmarks/replay.py
  ```
- [ ] Terminology consistency: "World Policy" / "World Manifest" used consistently.
- [ ] Layer numbering (L1=Input Boundary, L5=Execution Boundary) consistent in all docs and code comments.
- [ ] No `TECHNICAL_SPEC.md` references remain (replaced by `ARCHITECTURE.md`).
  ```bash
  grep -r "TECHNICAL_SPEC" . --include="*.md" --include="*.py"
  ```
- [ ] All source packages importable: `src/boundary/`, `src/compiler/`, `src/policy/`, `src/provenance/`, `src/gateway/`.
- [ ] `PROJECT_TASKS.md`: all issues #1–#34 marked `[x]` (except #27 closed as duplicate).
