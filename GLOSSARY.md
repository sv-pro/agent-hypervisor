# Agent Hypervisor — Glossary

*Derived from SCENARIO-zombie-agent.md*
*Terms are added as they appear in scenarios. No term exists without a scenario referencing it.*

---

## Core Pipeline

**Semantic Event**
A structured representation of an input, produced at the virtualization boundary.
Never raw text. Always carries: `source`, `trust_level`, `tainted`, `sanitized_payload`.
The agent only ever sees Semantic Events — never raw reality.

**Proposed Action**
A structured request from the agent to affect the world.
The agent cannot act directly. It proposes. The hypervisor decides.
Format: `action_type`, `parameters`, `provenance_chain`.

**Manifest Resolution**
The deterministic process of evaluating a Proposed Action against the World Manifest.
Produces exactly one of: `ALLOW`, `DENY`, `ASK`.
No LLM involved. Same input → same output, always.

---

## World Definition

**World Manifest**
The formal specification of everything that exists in the agent's universe.
Defines: trust channels, capabilities per trust level, permitted actions and their schemas,
invariants, escalation conditions, provenance requirements.
Compiled into deterministic runtime artifacts. Not a config file — a constitution.

**Manifest Extension**
The act of adding a new explicit rule to the World Manifest in response to an ASK.
Distinct from one-shot approval: extension changes the world permanently.
Requires human review. Produces a new compiled manifest version.

**Action Ontology**
The set of actions that exist in the agent's world, as defined by the World Manifest.
Actions outside the ontology cannot be proposed — they do not exist.

---

## Trust & Taint

**Trust Level**
A property of an input channel, not of content.
Defined in the World Manifest per source: `trusted`, `untrusted`, `derived`.
`derived` means trust is inherited from the provenance chain of source data.

**Taint**
A property of data indicating it originated (directly or transitively) from an untrusted source.
Taint is not a label that can be removed by the agent. It propagates through transformations.
Governed by Taint Propagation Rules in the World Manifest.

**Provenance Chain**
The full lineage of a data object: original source, trust level at origin,
all transformations applied, sessions crossed.
Required on every memory write. Preserved across sessions.
The mechanism by which taint survives session boundaries.

---

## Capabilities

**Capability**
A named permission class that must be present for an action to be allowed.
Capabilities are granted per trust level, not per tool.
Examples: `read`, `internal_write`, `memory_write`, `external_side_effects`.
An action requiring a capability absent from the current trust context is denied —
not filtered, but ontologically unavailable.

**Capability Matrix**
The mapping of trust levels to capability sets, defined in the World Manifest.
Compiled into a static lookup table at manifest compilation time.

---

## Invariants

**Invariant**
A physics law of the agent's world. Cannot be overridden by manifest rules.
Always enforced before manifest lookup. Violation → immediate DENY.

**TaintContainmentLaw**
Invariant: tainted data cannot trigger `external_side_effects`.
Enforcement: DENY, regardless of manifest rules or user approval.

**ProvenanceLaw**
Invariant: `memory_write` requires provenance metadata.
A memory write without provenance is rejected unconditionally.

**CapabilityBoundaryLaw**
Invariant: an action cannot execute without the required capability present
in the current trust context.

---

## Resolution Outcomes

**ALLOW**
The proposed action is explicitly permitted by the manifest and violates no invariants.
Executes immediately. Logged with full provenance.

**DENY**
The proposed action is explicitly denied by the manifest, or violates an invariant.
Does not execute. Logged with the specific rule triggered and provenance chain.

**ASK**
The proposed action is not covered by the manifest and violates no invariants.
Available only in interactive mode. Presents to the user:
— what action is proposed
— why (agent's reasoning)
— where the data came from (provenance)
— two choices: one-shot approval or manifest extension.
In background mode, uncovered actions resolve to DENY.

---

## Execution Modes

**Workflow Definition Mode**
The human defines and extends the agent's world.
Produces or updates the World Manifest.
ASK in this mode always offers manifest extension as the primary path.

**Interactive Execution Mode**
The agent executes within the defined world, with the user present.
Uncovered actions → ASK. User can approve once or extend the manifest.

**Background Execution Mode**
The agent executes without the user present.
Only explicitly allowed actions execute.
Uncovered actions → DENY. Logged for review in the next interactive session.

---

## Architecture Boundary

**Core**
The hypervisor framework. Implements: manifest loading, manifest resolution,
taint propagation, provenance tracking, capability lookup, invariant enforcement.
No UI. No scenario-specific logic. Language-independent interface.
Must have zero dependency on Demo.

**Demo**
The scenario runner. Implements: specific scenarios, user interaction (ASK dialogs),
visualization of events and decisions.
Depends on Core (via defined interface). Core does not know Demo exists.
