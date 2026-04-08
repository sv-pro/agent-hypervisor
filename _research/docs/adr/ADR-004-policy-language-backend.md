# ADR-004 — Policy Language Backend: Datalog vs. Rego vs. Cedar

**Status:** Open
**Phase:** v0.4
**Raised:** 2026-03-15

---

## Question

Which policy language should become the primary backend for the World Policy engine, replacing the current hand-written Python predicate tables?

A secondary question: should Cedar be considered for the actor/resource/action subset of decisions even if it is not the primary backend?

---

## Context

The current policy engine compiles YAML manifest rules into flat Python predicate tables (`agentdojo-bench/ah_defense/intent_validator.py`, `taint_tracker.py`). Known expressiveness limits:

- Taint propagation rules are operation→label mappings with no compositional semantics (cannot express cross-entity propagation or lineage depth constraints)
- Escalation conditions are conjunctive only — no disjunctions or temporal constraints
- No formal proof of rule completeness or non-interference between rules
- No intrinsic explainability — audit traces are hand-constructed

The v0.4 roadmap requires prototyping at least Datalog and Rego before making a selection.

---

## Assessment

| Property | Datalog | Rego (OPA) | Cedar |
| --- | --- | --- | --- |
| **Taint propagation** | Excellent — recursive facts model propagation graphs natively | Good — explicit chaining required | Limited — not designed for data-flow tracking |
| **Provenance-aware policy** | Excellent — provenance as first-class relations | Good — provenance as structured JSON facts | Weak — no native provenance model |
| **Cross-entity reasoning** | Excellent — joins across entity relations are native | Good — document joins possible but verbose | Weak — designed for single entity/resource decisions |
| **Runtime enforcement** | Good — Souffle/DLite compile to efficient native code | Good — OPA Wasm runtime, <5ms typical | Excellent — Cedar designed for high-throughput authorization |
| **Design-time compilation** | Excellent — Datalog programs compile ahead of time; static analysis possible | Good — partial evaluation via `opa build` | Good — static analysis tooling exists |
| **Explainability / audit** | Good — proof trees derivable from facts | Excellent — built-in decision logs, `opa eval --explain` | Good — Cedar evaluation trace is readable |
| **Integration complexity** | Medium — Python bindings: pyDatalog (pure Python), Souffle (native, better performance) | Low — REST API or embedded Wasm; mature ecosystem, pip-installable | Medium — Rust-native; Python bindings exist but less mature |
| **Ecosystem maturity** | Medium — academic roots, production use in Datomic/LDBC | High — production use in OPA/Styra, large community | Medium — AWS production use, growing community |
| **Fit with AH World Manifest** | Highest — manifest actions/rules as extensional DB; 7-step validation as derivation | High — manifest as policy bundle; runtime state as structured input | Medium — best fit for actor/resource/action triples; world model may not map cleanly |

---

## Secondary Question: Cedar for Actor-Scoped Decisions

Cedar's entity model (principal, action, resource) maps well to the capability matrix subset of AH decisions: "can actor X perform action Y on resource Z given trust level T?" This is structurally different from taint propagation (which is a graph problem) and may be better served by Cedar even if Datalog handles taint.

A hybrid architecture is possible: Datalog for taint/provenance reasoning, Cedar for actor/capability authorization. The Policy IR would route decisions to the appropriate backend by decision type.

This adds complexity and is not recommended for v0.4 prototyping. Revisit if the Datalog prototype shows poor fit for capability matrix decisions specifically.

---

## Prototype Experiment (v0.4)

**Minimal Datalog experiment:**

Express the workspace manifest taint rules and the 7-step validation pipeline as Datalog facts + rules using pyDatalog. Run the AgentDojo workspace benchmark with both the Datalog backend and the current Python engine. Compare:

1. Decision correctness (equivalence test suite — must be 100%)
2. Decision latency (target: within 2× of Python baseline)
3. Rules expressible in Datalog that cannot be expressed in the current YAML taint_rules format (target: at least one)

**Minimal Rego experiment:**

Express the same rules as an OPA policy bundle. Run the same equivalence test suite and latency benchmark.

**Equivalence test suite:**

For each scenario in the AgentDojo workspace benchmark, the Datalog engine, the Rego engine, and the current Python engine must produce identical verdicts (allow/deny/require_approval) and identical reason codes.

---

## Criteria for Resolution

- Equivalence test suite pass rate (must be 100% for a backend to be a candidate)
- Decision latency within 2× of Python baseline for single-decision evaluation
- At least one taint propagation rule expressible in the new language but not in the current YAML format
- Subjective: manifest authors find the policy language readable after brief familiarization

---

## Current Lean

Prototype Datalog first. The World Policy engine is fundamentally a provenance graph reasoning problem. Datalog is the canonical language for this class of reasoning. If the Datalog prototype meets the latency constraint and reveals no fundamental fit problems, it becomes the recommendation. Rego is the fallback if Datalog integration complexity proves prohibitive.

---

## Resolution Trigger

Decision to be made when both prototypes pass the equivalence test suite. Output: an ADR with a concrete recommendation and benchmark evidence, targeting v0.5 production adoption.
