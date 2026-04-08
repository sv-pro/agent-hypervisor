# Capability Rendering

**Capability Rendering** is the process by which a world manifest is resolved
into the concrete execution surface that an agent operates against. It is a
product-level primitive: not a runtime check, not a filter, but the act of
constructing the surface itself.

---

## Raw tools vs rendered capabilities

**Raw tools** are ambient capability. They are execution primitives that exist
in the environment — functions the runtime *could* invoke. They carry no
access control, no argument constraints, and no visibility rules. Their
existence in the environment does not mean anything can call them.

```
# Raw tools — ambient, unconstrained
send_email(to, body)
delete_record(id)
read_data()
export_to_s3(bucket, key)
```

**Rendered capabilities** are the constrained execution surface visible to an
agent in a specific session. They are constructed from a world manifest.
Each rendered capability is a named, typed form that narrows a raw tool to
the exact conditions under which it may be invoked. The agent sees only the
rendered capabilities — not the raw tools beneath them.

```
# Rendered capabilities — constrained, explicit, visible to the agent
send_internal_email   →  send_email, to must match @company.com
send_report_to_security  →  send_email, to is always security@company.com (fixed)
read_data             →  read_data, no arguments
```

The rendered surface is always smaller than the ambient tool set. Capabilities
that are not rendered are not merely blocked — they do not appear on the
surface at all.

---

## From manifest to rendered surface

Rendering proceeds in one direction: manifest in, surface out.

```
World Manifest
  │
  │  (enumerate allowed capabilities)
  │  (resolve value sources)
  │  (apply parameter constraints)
  ▼
Rendered Capability Surface
  │
  │  (agent operates here)
  ▼
Enforcement Engine
```

The **world manifest** is the authoritative definition: which capability names
are allowed, how each argument may be sourced, and what constraints apply.

The **rendered capability surface** is the concrete result: a set of named,
callable capabilities with fully specified parameter contracts. This is the
only interface the agent has access to.

The **enforcement engine** evaluates each call against the rendered capability
definition — verifying argument sources and constraint satisfaction before
passing the call to the underlying tool.

### What rendering does

| Step | Description |
|------|-------------|
| Enumerate | Only capabilities declared in the manifest appear on the surface |
| Resolve sources | Each argument's value source is fixed (`literal`, `actor_input`, `resolver_ref`, `context_ref`) |
| Apply constraints | Each `actor_input` argument carries its declared constraint (`email`, `text`, `enum`) |
| Absent tools | Any raw tool not referenced by an allowed capability does not exist on the surface |

---

## Agent visibility

The agent operates entirely within the rendered surface. It has no visibility
into the raw tool layer beneath it.

**Allowed capabilities** are present on the surface with their full parameter
contracts. The agent can call them subject to declared constraints.

**Forbidden actions are absent.** A raw tool that has no rendered capability
in the current manifest is not visible to the agent. It cannot be requested,
referenced, or addressed. There is no call to reject because there is nothing
to call.

```
# Raw tool present in the environment
delete_record(id)

# No capability renders delete_record in this manifest
# → delete_record does not exist on the agent's surface
# → agent cannot form a call to it
# → no decision is required at runtime
```

This is the structural guarantee that Capability Rendering provides. The agent
cannot reach what was never constructed.

---

## Construction, not filtering

A filter receives a request and decides whether to allow it. The request exists
before the filter runs. The filter's job is to reject the bad ones.

Capability Rendering works differently. It constructs the surface before any
request is formed. The agent never sees the options that were not rendered.
There is nothing for a filter to catch because the request cannot be formed.

| | Filtering | Capability Rendering |
|--|-----------|----------------------|
| **What exists** | All tools, then reduced at runtime | Only rendered capabilities |
| **Agent visibility** | Full tool set; some requests rejected | Rendered surface only |
| **Forbidden action** | Rejected after the agent requests it | Absent; the agent cannot request it |
| **Security property** | Correct rejection of bad requests | Structural impossibility of bad requests |
| **When decided** | At call time | At surface construction time |

### Attack surface reduction

Capability Rendering reduces attack surface by reducing the surface that
exists. An agent cannot be manipulated into calling a tool it cannot see. A
prompt injection attack that instructs the agent to call `delete_all_data`
produces no effect if `delete_all_data` was never rendered — the agent has no
capability to address.

The reduction is not probabilistic. It does not depend on the quality of
rejection logic or the robustness of a classifier. It is structural: fewer
things exist, so fewer things can go wrong.

---

## Relationship to the DSL

The Capability DSL ([`capability-dsl.md`](capability-dsl.md)) is the language
used to author world manifests. A manifest written in the DSL is the input to
the rendering step.

Each capability definition in the DSL becomes exactly one entry on the rendered
surface. Each `base_tool` reference in a capability definition resolves to the
underlying raw tool at enforcement time — never at authoring time, and never
exposed to the agent.

The DSL enforces that:
- Every capability references a declared tool (base tool must exist)
- Every argument has exactly one declared value source
- Every constraint is structurally valid

These checks happen at parse and validation time. By the time a surface is
rendered, the manifest is already known to be well-formed.

---

## Summary

| Concept | Definition |
|---------|------------|
| Raw tool | An execution primitive in the ambient environment. Carries no policy or visibility rules. |
| Capability | A constrained, named form over a raw tool. Defines how each argument may be sourced and constrained. |
| World manifest | The authoritative definition of which capabilities exist and how they are constrained in a given context. |
| Rendered capability surface | The concrete set of callable capabilities constructed from the manifest. This is what the agent sees. |
| Capability Rendering | The process of resolving a manifest into a rendered surface. Not filtering — construction. |
| Absent capability | A raw tool or action with no rendered capability in the current manifest. Does not exist on the agent's surface. |

Capability Rendering is the mechanism by which intent ("the agent should be
able to do X") becomes structure ("the surface the agent operates against
contains exactly X"). Everything else in the stack — enforcement, constraints,
audit — operates on the surface that rendering produces.
