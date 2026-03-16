# Execution Governance — Architecture Diagram

This document provides a visual reference for how the Agent Hypervisor
implements execution governance: the enforcement of policy at the boundary
between an agent deciding to call a tool and the tool actually running.

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent / LLM Runtime                      │
│                                                                 │
│  Agent reasons about a task and proposes a tool call:           │
│                                                                 │
│    send_email(                                                  │
│      to   = "alice@company.com"  [provenance: user_declared]   │
│      body = "Q3 report"          [provenance: system]          │
│    )                                                            │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │  proposed ToolCall
                               │  (with provenance labels per argument)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent Hypervisor                           │
│                                                                 │
│  Intercepts every proposed tool call before execution.          │
│  Evaluates each argument's provenance chain.                    │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │               Provenance Chain Resolution                 │  │
│  │                                                           │  │
│  │  For each argument, walks the full derivation DAG.        │  │
│  │  A derived value inherits the least-trusted provenance    │  │
│  │  of all its parents — provenance cannot be laundered.     │  │
│  │                                                           │  │
│  │  external_document < derived < user_declared < system     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                               │                                 │
│                               ▼                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     Policy Engine                         │  │
│  │                                                           │  │
│  │  Evaluates declarative YAML rules in order.               │  │
│  │  Each rule matches on: tool, argument, provenance, role.  │  │
│  │  Verdict precedence: deny > ask > allow                   │  │
│  │                                                           │  │
│  │  Example rules:                                           │  │
│  │    deny  send_email  to=external_document                 │  │
│  │    ask   send_email  to=user_declared                     │  │
│  │    allow read_file   (any provenance)                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                               │                                 │
│                               ▼                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                  Provenance Firewall                       │  │
│  │                                                           │  │
│  │  Structural rules that enforce invariants regardless of   │  │
│  │  policy YAML.  Cannot be overridden by policy rules.      │  │
│  │                                                           │  │
│  │  RULE-01: external_document → side-effect sink → deny    │  │
│  │  RULE-02: extracted_recipients → send_email → deny       │  │
│  │  RULE-03: provenance laundering (derived chain) → deny   │  │
│  │  RULE-04: mixed provenance on sensitive arg → deny       │  │
│  │  RULE-05: external_document body → http_post → deny      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                               │                                 │
│                               ▼                                 │
│            Merge verdicts:  deny > ask > allow                  │
│                               │                                 │
└───────────────────────────────┼─────────────────────────────────┘
                                │
          ┌─────────────────────┼──────────────────────┐
          │                     │                      │
          ▼                     ▼                      ▼
       ALLOW                   ASK                  DENY
          │                     │                      │
          │             ┌───────┴────────┐             │
          │             │ Approval       │             │
          │             │ Workflow       │             │
          │             │                │             │
          │             │ Execution held │             │
          │             │ pending human  │             │
          │             │ review.        │             │
          │             │ approval_id    │             │
          │             │ returned.      │             │
          │             └───────┬────────┘             │
          │                     │                      │
          │          ┌──────────┴──────────┐           │
          │          │                     │           │
          │       approved             rejected        │
          │          │                     │           │
          ▼          ▼                     ▼           ▼
   ┌──────────────────────────────────────────────────────┐
   │                  Tool Execution                      │
   │                                                      │
   │  Allowed calls execute; denied/rejected calls do not │
   └──────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────┐
   │                    Trace Store                       │
   │                                                      │
   │  ALL decisions recorded (allow, deny, ask).          │
   │  Fields: tool, verdict, matched_rule, arg_provenance │
   │          trace_id, approval_id, policy_version       │
   │                                                      │
   │  Trace data feeds the Policy Tuner for offline       │
   │  governance analysis and policy improvement.         │
   └──────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **Agent / LLM Runtime** | Reasons about tasks; proposes tool calls with provenance labels on every argument |
| **Provenance Chain Resolution** | Walks the derivation DAG to determine the effective (least-trusted) provenance of each argument |
| **Policy Engine** | Evaluates declarative YAML rules to produce a verdict (allow / ask / deny) |
| **Provenance Firewall** | Enforces structural rules that cannot be overridden by policy — the last line of defence |
| **Approval Workflow** | Holds 'ask' verdicts pending human review; records approver identity and decision |
| **Tool Execution** | Executes allowed tool calls; blocked calls never reach this stage |
| **Trace Store** | Append-only audit log of every governance decision, including policy version at decision time |
| **Policy Tuner** | Offline analysis of trace data to detect patterns, generate improvement suggestions |

---

## Provenance Trust Ordering

```
  Least trusted                                       Most trusted
  ─────────────────────────────────────────────────────────────────
  external_document  <  derived  <  user_declared  <  system
  ─────────────────────────────────────────────────────────────────
  Files, emails,        Computed     Operator-declared  Hardcoded
  web pages,            from parents  in task manifest   by system
  agent outputs         (inherits                        (no user
  (untrusted)           least-trusted                    influence)
                        parent)
```

Provenance is **sticky**: a value derived from an `external_document`
carries `external_document` provenance even after transformation.
This prevents provenance laundering — wrapping untrusted data does not
make it trusted.

---

## Three-Way Verdict System

```
  Proposed ToolCall
         │
         ▼
  ┌─────────────┐     ┌──────────────────────────────────────────┐
  │   Policy    │────►│ allow — execute immediately              │
  │   Engine    │     │         result returned to agent         │
  │      +      │     ├──────────────────────────────────────────┤
  │ Provenance  │────►│ deny  — blocked, never executes          │
  │  Firewall   │     │         reason and trace recorded        │
  │             │     ├──────────────────────────────────────────┤
  └─────────────┘────►│ ask   — held pending human approval      │
                      │         approval_id returned to agent    │
                      │         human reviews and approves/rejects│
                      └──────────────────────────────────────────┘
```

Verdict precedence guarantees the most restrictive verdict wins when
multiple rules match: `deny` overrides `ask`, which overrides `allow`.

---

## Governance Loop (Policy Tuner)

```
  Runtime Traces
       │
       │  (offline analysis)
       ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     Policy Tuner                           │
  │                                                             │
  │  PolicyAnalyzer                                             │
  │    Pass 1: Friction signals  (repeated asks/denies/approvals│
  │    Pass 2: Risk signals      (allows on dangerous sinks)    │
  │    Pass 3: Scope drift       (rules surviving all versions) │
  │    Pass 4: Rule quality      (broad allows, catch-all deny) │
  │                                                             │
  │  SuggestionGenerator                                        │
  │    Maps signals/smells → conservative candidate actions     │
  │    Includes: risk score, usage count, scope reduction hints │
  │                                                             │
  │  TunerReporter                                              │
  │    Outputs: JSON (machine-readable) or Markdown (review)    │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 │  human policy operator reviews
                                 ▼
                          Policy Updated
                          (if warranted)
```

The Policy Tuner **never modifies the policy automatically**.
All suggestions require human review before any change is made.

---

## Integration Points

```
  ┌──────────────┐       ┌───────────────────────────────────┐
  │  LangChain / │       │         Agent Hypervisor          │
  │  LangGraph   │──────►│  POST /tools/execute              │
  │  Agent       │       │  {tool, arguments, provenance}    │
  └──────────────┘       └───────────────────────────────────┘

  ┌──────────────┐       ┌───────────────────────────────────┐
  │  MCP Client  │       │      MCP Gateway Adapter          │
  │  (any tool   │──────►│  (translates JSON-RPC to HTTP)    │
  │   framework) │       │  → Agent Hypervisor Gateway       │
  └──────────────┘       └───────────────────────────────────┘

  ┌──────────────┐       ┌───────────────────────────────────┐
  │  In-process  │       │   InProcessHypervisor             │
  │  Python agent│──────►│   (no HTTP — direct evaluation)   │
  │  (demo/test) │       │   see: ide_agent_governance_demo  │
  └──────────────┘       └───────────────────────────────────┘
```

See [gateway_architecture.md](gateway_architecture.md) for the full HTTP API reference.
See [mcp_integration.md](mcp_integration.md) for MCP integration details.
