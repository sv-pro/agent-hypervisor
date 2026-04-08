# Bounded Semantic Space

## 1. Concept

The Agent Hypervisor bounds what an agent can **do** (World Manifest) and what
can **execute** (Capability Matrix). The Semantic Space extension bounds what an
agent can **express, reason about, and commit to**.

Language is not just input — it is an interface. Fully expressive natural
language means every phrase, framing, and instruction can potentially influence
behavior. The Semantic Space closes this surface.

**Key property**: Expressions that fall outside the semantic space are not
*rejected* — they are *non-representable*. There is no "no". The input simply
has no form in this deployment.

---

## 2. Semantic Primitives

A Semantic Primitive is an atomic unit of expressible meaning. The Semantic
Manifest registers which primitives exist for a given deployment.

Four primitive kinds (exhaustive):

| Kind | Description | Example |
|---|---|---|
| `action_intent` | Intent to invoke a state-changing action | "initiate a return for order ORD-123" |
| `query_intent` | Intent to read or inspect state (no side effects) | "what is the status of order ORD-123?" |
| `commitment` | A binding promise, guarantee, or quantified offer | "apply 10% discount to order ORD-123" |
| `reasoning_pattern` | A structured cognitive operation (no tool call) | "compare shipping options by price" |

Every expression in the system must be one of these four kinds. Expressions that
cannot be classified and matched to a registered primitive have no representation.

**Commitment primitives** are the most tightly controlled. They carry:
- An explicit enum of authorized parameter values (e.g. discount tiers)
- Required capability identifiers (must be present in the capability matrix)
- A direct link to a World Manifest action

An unauthorized commitment value (e.g. `50_pct` when only `[5_pct, 10_pct]`
are registered) fails parameter validation and is NonRepresentable before any
capability check occurs.

---

## 3. Semantic IR

The Semantic IR is the typed intermediate representation produced by the semantic
mapping step. It sits between natural language input and the existing Intent IR.

```
natural language input
    │
    ▼
[SemanticMapper]           ← LLM (online)
    │                        Reads input, proposes CandidateExpression
    │ CandidateExpression     { primitive_id, parameters, source_text }
    ▼
[SemanticValidator]        ← DETERMINISTIC (no LLM)
    │                        Validates candidate against SemanticManifest
    ├── SemanticExpression            → IntentMapper → IntentProposal → WorldPolicy
    ├── NonRepresentableExpression    → pipeline terminates (zero side effects)
    └── CapabilityRequiredExpression  → pipeline terminates (capability audit)
```

The LLM's role ends when it produces a `CandidateExpression`. From that point,
all decisions are deterministic. Same manifest + same candidate = same outcome.

### Three Outcome Types

**`SemanticExpression`** — fully representable, flows into the existing pipeline.

```python
SemanticExpression(
    primitive_id="apply_standard_discount",
    primitive_kind=PrimitiveKind.COMMITMENT,
    parameters={"tier": "10_pct", "order_id": "ORD-123"},
    source_text="give 10% discount to order #ORD-123",
    requires_capabilities=("DISCOUNT_LEVEL_1",),
)
```

**`NonRepresentableExpression`** — no representation exists.

```python
NonRepresentableExpression(
    source_text="give 50% discount to order #ORD-123",
    reason="Parameter 'tier' value '50_pct' not in allowed set: ('5_pct', '10_pct')",
    nearest_primitives=("apply_standard_discount", "apply_loyalty_discount"),
)
```

**`CapabilityRequiredExpression`** — primitive exists, capability absent.

```python
CapabilityRequiredExpression(
    primitive_id="apply_standard_discount",
    primitive_kind=PrimitiveKind.COMMITMENT,
    source_text="give 10% discount to order #ORD-123",
    missing_capability="DISCOUNT_LEVEL_1",
    available_capabilities=("QUERY_ONLY",),
)
```

---

## 4. Non-Representability as First-Class Outcome

Non-representability is not an error state. It is the correct system response
to inputs outside the bounded semantic space.

The system does not produce a rejection message. The input terminates at the
semantic layer with no side effects, no IntentProposal, and no WorldPolicy
evaluation. This is ontological absence, not prohibition.

**Validation algorithm** (deterministic, ordered, fail-closed):

```
1. Is candidate.primitive_id registered in the manifest?
   No  → NonRepresentableExpression

2. Do candidate.parameters satisfy all ParameterSpec constraints?
   No  → NonRepresentableExpression

3. Are all primitive.requires_capabilities present in available_capabilities?
   No  → CapabilityRequiredExpression

4. All checks pass → SemanticExpression
```

Default behavior when no primitive matches: NonRepresentable (fail-closed, not
fail-open). Unknown inputs cannot accidentally become valid expressions.

---

## 5. "give 50% discount" — Full Trace

```
Input:  "give 50% discount to order #ORD-123"
Agent capability set: {DISCOUNT_LEVEL_1, QUERY_ONLY}

SemanticMapper (LLM) produces CandidateExpression:
    {
      "primitive_id": "apply_standard_discount",
      "parameters":   {"tier": "50_pct", "order_id": "ORD-123"},
      "alternatives": ["apply_loyalty_discount"]
    }

SemanticValidator (deterministic):
    Step 1: 'apply_standard_discount' in manifest?   YES
    Step 2: tier='50_pct' in enum ('5_pct', '10_pct')?  NO

    → NonRepresentableExpression:
        source_text:        "give 50% discount to order #ORD-123"
        reason:             "Parameter 'tier' value '50_pct' not in
                             allowed set: ('5_pct', '10_pct')"
        nearest_primitives: ("apply_standard_discount", "apply_loyalty_discount")

Pipeline: terminates at SemanticValidator.
No IntentProposal created. No WorldPolicy evaluated. No tool called.
```

**Variant — capability absent:**

```
Input:  "give 10% discount to order #ORD-123"
Agent capability set: {QUERY_ONLY}    (DISCOUNT_LEVEL_1 absent)

SemanticValidator:
    Step 1: primitive exists?        YES
    Step 2: tier='10_pct' valid?     YES (in enum)
    Step 3: DISCOUNT_LEVEL_1 present? NO

    → CapabilityRequiredExpression:
        missing_capability:    "DISCOUNT_LEVEL_1"
        available_capabilities: ("QUERY_ONLY",)

Pipeline: terminates at SemanticValidator.
```

**Variant — authorized request:**

```
Input:  "give 10% discount to order #ORD-123"
Agent capability set: {DISCOUNT_LEVEL_1, QUERY_ONLY}

SemanticValidator:
    Step 1: primitive exists?        YES
    Step 2: tier='10_pct' valid?     YES
    Step 3: DISCOUNT_LEVEL_1 present? YES

    → SemanticExpression (flows into IntentMapper → WorldPolicy)
```

---

## 6. Design-Time Compilation

The Semantic Manifest is not written from scratch by hand. The `SemanticCompiler`
uses an LLM offline to extract primitives from workflow definitions.

```
workflow_definitions.yaml
    │
    ▼ SemanticCompiler (LLM-assisted, offline)
    │   1. extract_patterns  — what intents appear in these workflows?
    │   2. propose_primitives — canonicalize into typed primitives
    │   3. generate_edge_cases — adversarial inputs that should NOT match
    │
    ▼
draft_semantic_manifest.yaml    ← human review required
    │
    ▼
semantic_manifest.yaml          ← committed to version control
    │
    ▼
runtime artifacts               ← loaded by SemanticValidator at startup
                                   no LLM present past this point
```

**Edge case generation** produces adversarial inputs for each primitive — inputs
that attempt to map to the primitive but should not. These are reviewed alongside
the draft manifest to catch boundary errors before deployment.

The LLM is used only during compilation. The runtime validation path has zero
LLM dependency.

---

## 7. Relationship to Existing Hypervisor Stages

```
Stage              Component                   Bounds
────────────────────────────────────────────────────────────────────────────
Layer 1            Input Boundary              Trust channel, taint label
                   SemanticEvent               Structured typed input

[NEW] Layer 2a     Semantic Manifest           What meanings exist
                   SemanticValidator           Deterministic primitive validation
                   SemanticExpression          Typed meaning representation

Layer 2b           World Manifest              What actions exist
                   IntentProposal              Typed action intent

Layer 4            Capability Matrix           Trust level → permitted side effects
                   WorldPolicy                 Deterministic execution gate

Layer 5            Execution Boundary          Tool invocation, audit log
────────────────────────────────────────────────────────────────────────────
```

The Semantic layer operates before the World Manifest layer. An expression must
be *representable* before it can be *permitted*.

Two ontological boundaries now exist:

| Boundary | Question |
|---|---|
| Semantic Manifest | "Does this *intent* exist in this deployment?" |
| World Manifest | "Does this *action* exist in this deployment?" |

An intent that does not exist cannot become an action. An action that does not
exist cannot be executed. Two independent layers of ontological containment.

---

## 8. Security Properties

**Prompt injection**

Injected instructions ("ignore all previous instructions", "you are now a
different agent") cannot form a valid `SemanticExpression`. No registered
primitive has kind `meta_instruction` or maps to a system configuration tool.
Result: NonRepresentable. The injection never reaches WorldPolicy.

**Unauthorized commitments**

A discount at an unauthorized tier (50%) fails enum parameter validation.
The expression is NonRepresentable before any capability check.
A discount at an authorized tier (10%) but without the capability is
CapabilityRequired — blocked at the semantic layer, not by WorldPolicy.

**Unintended tool invocation**

A tool can only be invoked if a `SemanticExpression` with a matching
`maps_to_action` field exists and reaches the IntentMapper. If no registered
primitive maps to a tool, that tool is unreachable through the semantic layer —
regardless of what the World Manifest permits.

**Invalid reasoning patterns**

Out-of-domain reasoning ("simulate a nuclear reactor", "hypothesize an
unrestricted version of yourself") has no registered `reasoning_pattern`
primitive and is NonRepresentable.

---

## 9. Schema and Implementation Reference

| Artifact | Path |
|---|---|
| Primitive types | `src/semantic/primitives.py` |
| Semantic IR types | `src/semantic/semantic_ir.py` |
| Manifest model + YAML loader | `src/semantic/semantic_manifest.py` |
| Runtime validator (deterministic) | `src/semantic/semantic_validator.py` |
| Design-time compiler (LLM-assisted) | `src/semantic/semantic_compiler.py` |
| Schema reference | `manifests/semantic_manifest_schema.yaml` |
| Customer support example manifest | `manifests/examples/customer_support_semantic.yaml` |
| Discount authorization trace | `examples/semantic/discount_example.py` |
