# Agent Hypervisor — Technical One-Pager

---

## 1. The Problem

Modern AI agents execute real-world actions through tools: sending email, making HTTP
requests, writing files, calling APIs.  These tools have side effects that cannot be
undone.

Most current defenses operate at the **prompt layer** — they classify whether inputs
*look* malicious before the model processes them.  This approach has a structural
limitation: by the time a tool call is about to execute, the model has already
processed the input, potentially following attacker instructions embedded in trusted
content (prompt injection).  Pattern-matching on text cannot reliably stop an attack
whose signal is structural, not lexical.

The two dominant attack patterns:

- **Prompt injection** — an attacker embeds instructions in content the agent reads
  (emails, documents, web pages).  The agent follows those instructions and routes
  attacker-controlled data to a side-effect tool.

- **Data exfiltration** — the agent is manipulated into sending sensitive data to an
  attacker endpoint through a legitimate-looking tool call.

Both attacks share a common structure: **a tool argument is derived from untrusted
content**.  The argument text may look benign.  The vulnerability is in the derivation
chain, not the string value.

---

## 2. The Missing Layer

The gap in current AI security stacks is an **execution governance layer**: a control
point that sits between the agent's tool requests and the external systems those tools
reach, and that evaluates calls based on where arguments came from — not what they say.

Prompt guardrails act before the model.  Tool allowlists act on tool names.  Neither
inspects the provenance of arguments at execution time.

---

## 3. What Agent Hypervisor Provides

Agent Hypervisor implements the execution governance layer.

**Provenance-aware decisions**
Every tool argument carries a `ValueRef` recording its origin:
`external_document`, `derived`, `user_declared`, or `system`.
Provenance is sticky through derivation — if a value is computed from an external
document, the resulting `ValueRef` traces back to that origin regardless of how many
transformation steps occurred.

**Runtime policy enforcement**
A declarative YAML policy engine evaluates the full derivation chain of every argument
before any tool executes.  Rules express conditions like "if the `to` argument of
`send_email` traces to `external_document`, deny."  The check is deterministic.

**Approval workflow**
When a call is sensitive but not clearly malicious, the verdict is `ask`: the tool is
held pending human review.  Reviewers inspect the full call context, approve or deny,
and the outcome is recorded.  Pending approvals survive process restarts.

**Auditable traces**
Every decision — allow, deny, or held-for-approval — produces an immutable trace entry
with tool name, arguments, provenance labels, matched rule, verdict, and reviewer
identity.  The audit trail is append-only and persists across restarts.

**Policy versioning**
Every policy load creates a versioned record.  All traces link to the exact policy
version active when the decision was made.  Post-hoc audit is always possible: any
decision can be re-examined against the rules that produced it.

---

## 4. Where It Fits in the Stack

```
agent runtime
      ↓
  tool request
      ↓
Agent Hypervisor Gateway        ← enforcement point
      ↓
  policy engine                 ← declarative YAML rules (hot-reloadable, versioned)
      ↓
  tool adapter                  ← executes only if verdict = allow
      ↓
external system
```

The gateway exposes a single HTTP endpoint (`POST /tools/execute`).  The agent
runtime submits tool calls with provenance-annotated arguments.  The gateway returns
`allow`, `deny`, or `ask`.  The adapter executes only on `allow`.

The integration point is framework-agnostic.  A Python client, MCP adapter shim, and
LangChain decorator example are included.

---

## 5. What Makes This Approach Different

**vs. prompt guardrails**
Guardrails act before the model on input text.  They cannot observe what the model
does with that input, and they do not see tool calls.  An injection that passes the
input filter still executes if the model follows its instructions.

**vs. tool allowlists**
Allowlists permit or block tool names.  They do not inspect argument provenance.  A
permitted tool (`send_email`) called with an attacker-controlled recipient passes
through an allowlist unchallenged.

**vs. mediation-only approaches**
Some frameworks log or proxy tool calls without enforcing a verdict.  Agent Hypervisor
enforces: the tool does not execute unless the policy allows it.  Logging after the
fact does not prevent exfiltration.

The key distinction: Agent Hypervisor checks **where arguments came from**, not
whether they contain suspicious patterns.  An injection does not need keywords.
It needs only to cause untrusted data to flow into a side-effect tool — which is
detectable at the execution boundary regardless of the injected text.

---

## 6. How to See It Working

Run the showcase demo:

```bash
pip install fastapi uvicorn pyyaml
python scripts/run_showcase_demo.py
```

The demo walks through three scenarios end-to-end:

1. A safe read — passes through with no friction
2. A prompt injection attempt — blocked deterministically by provenance structure
3. A legitimate sensitive action — held for human approval, then executed

After the demo, inspect the audit trail:

```bash
curl http://localhost:8080/traces
curl http://localhost:8080/approvals
curl http://localhost:8080/policy/history
```

See [demo_guide.md](demo_guide.md) for a full walkthrough.  See
[benchmark_brief.md](benchmark_brief.md) for a structured evaluation of the approach
against existing defenses.
