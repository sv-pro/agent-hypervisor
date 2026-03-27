# Capability DSL — v0.1

This document describes the Capability DSL: its concepts, structure, supported
constructs, validation rules, and worked examples.

---

## 1. Tools vs Capabilities

**Tools** are raw execution primitives. They are the actual functions the
runtime can invoke. A tool has a name and a set of parameter names. It carries
no policy, no constraints, no access control.

```
send_email(to, body)
summarize(content)
read_data()
```

**Capabilities** are constrained action forms over tools. A capability binds a
tool to specific rules about how each parameter may be sourced and what values
are acceptable. The actor (LLM or agent) interacts with capabilities, never
directly with tools.

The distinction matters: a tool describes *what can execute*. A capability
describes *under what conditions it may execute and with what inputs*.

Two capabilities can share the same base tool while enforcing entirely
different constraints:

```
send_internal_email   →  send_email, 'to' must be @company.com
send_report_to_security  →  send_email, 'to' is always security@company.com
```

---

## 2. DSL Structure

A registry definition is a mapping with three top-level keys:

```yaml
tools:       # raw execution primitives
resolvers:   # named value providers (declarations only)
capabilities: # constrained action forms
```

### 2.1 Tools

```yaml
tools:
  send_email:
    args: [to, body]
  summarize:
    args: [content]
  read_data:
    args: []
```

`args` lists the parameter names the tool accepts. If `args` is omitted, arg-name
validation is skipped for capabilities that reference the tool. An empty list
(`[]`) means the tool explicitly accepts no parameters.

### 2.2 Resolvers

```yaml
resolvers:
  escalation_contact_lookup:
    returns: email
  primary_security_contact:
    returns: email
```

Resolvers are **declarations only**. They are named references with a return
type. The DSL does not execute resolvers — the runtime is responsible for
binding resolver names to implementations. No code or expressions belong here.

### 2.3 Capabilities

```yaml
capabilities:
  <capability_name>:
    base_tool: <tool_name>
    args:
      <arg_name>:
        valueFrom: <value_source>
        constraints: <constraint>   # optional
```

Each capability names its `base_tool` and declares how each argument is
sourced and constrained.

---

## 3. Value Source Types

Every capability argument must declare exactly one `valueFrom` source.

### `literal`

The value is fixed at definition time. Actors cannot override it.

```yaml
to:
  valueFrom:
    literal:
      value: security@company.com
```

Use this when the destination or content must be hardcoded and must not be
influenced by any runtime input.

### `actor_input`

The value is supplied by the actor at call time. Subject to any declared
constraint.

```yaml
body:
  valueFrom:
    actor_input: {}
  constraints:
    kind: text
    max_length: 5000
```

### `context_ref`

The value is resolved from a named key in the execution context at call time.
The context is a structured, trusted data source — not arbitrary runtime state.

```yaml
sender:
  valueFrom:
    context_ref:
      ref: current_user_email
```

### `resolver_ref`

The value is resolved by a named resolver. The actor cannot supply or influence
the value. The resolver name must be declared in the `resolvers` section.

```yaml
to:
  valueFrom:
    resolver_ref:
      name: escalation_contact_lookup
```

---

## 4. Constraints

Constraints restrict the set of acceptable values for an argument. They apply
at enforcement time for `actor_input` values and at validation time for
`literal` values.

### `email`

Constrains the value to a valid email address.

```yaml
constraints:
  kind: email
  allow_domain: company.com   # optional
```

`allow_domain` restricts the address to a single domain. It is only valid for
`kind: email`.

### `text`

Constrains the value to a text string.

```yaml
constraints:
  kind: text
  max_length: 5000   # optional
```

### `enum`

Constrains the value to one of a fixed set of strings.

```yaml
constraints:
  kind: enum
  values: [low, medium, high]
```

---

## 5. Validation Rules

The validator performs semantic checks after parsing. All checks are
deterministic: the same input always produces the same result.

| Rule | Description |
|------|-------------|
| **base_tool exists** | Every capability must reference a tool declared in the `tools` section. |
| **arg name valid** | Every capability arg must appear in the base tool's `args` list. Skipped if the tool omits `args`. |
| **resolver_ref exists** | Every `resolver_ref` must reference a resolver declared in the `resolvers` section. |
| **literal domain check** | A `literal` value paired with `EmailConstraint(allow_domain=...)` must satisfy the domain restriction. |
| **allow_domain scope** | `allow_domain` is only valid for `kind: email`. Using it with `text` or `enum` is a parse error. |
| **unknown source kind** | Any `valueFrom` key not in `{literal, actor_input, context_ref, resolver_ref}` is a parse error. |
| **unknown constraint kind** | Any `kind` not in `{email, text, enum}` is a parse error. |

Parse errors (`ValueError`) are raised by the parser on structurally malformed
input. Semantic errors (`ValidationError`) are raised by the validator on
well-formed but semantically invalid input.

---

## 6. Worked Examples

### Example 1 — Literal-bound capability

The destination address is fixed in the capability definition. Actors supply
only the message body.

```yaml
capabilities:
  send_report_to_security:
    base_tool: send_email
    args:
      to:
        valueFrom:
          literal:
            value: security@company.com
      body:
        valueFrom:
          actor_input: {}
        constraints:
          kind: text
          max_length: 5000
```

The `to` field cannot be changed by the actor, by tainted input, or by prompt
injection. The destination is part of the capability definition, not of any
request.

---

### Example 2 — Domain-constrained actor input

The actor chooses the destination address, but it must be within `company.com`.
An address outside that domain is rejected.

```yaml
capabilities:
  send_internal_email:
    base_tool: send_email
    args:
      to:
        valueFrom:
          actor_input: {}
        constraints:
          kind: email
          allow_domain: company.com
      body:
        valueFrom:
          actor_input: {}
        constraints:
          kind: text
          max_length: 5000
```

This prevents exfiltration to external addresses while still allowing the actor
to address internal recipients.

---

### Example 3 — Resolver-based indirect value

The destination is resolved by a named resolver at call time. The actor cannot
supply or influence the address.

```yaml
capabilities:
  send_escalation:
    base_tool: send_email
    args:
      to:
        valueFrom:
          resolver_ref:
            name: escalation_contact_lookup
      body:
        valueFrom:
          actor_input: {}
        constraints:
          kind: text

resolvers:
  escalation_contact_lookup:
    returns: email
```

The resolver is a declaration. The runtime binds `escalation_contact_lookup` to
a concrete implementation. The DSL does not know or care what that
implementation is — only that it returns a value of type `email`.

---

## 7. What This Phase Does Not Cover

- **Enforcement**: this phase defines and validates capability shapes. Binding
  capabilities to the proxy enforcement layer is a subsequent step.
- **Executable resolvers**: resolvers are declarations. No code runs inside the DSL.
- **Provenance tracking**: taint and source classification are separate concerns
  (Phase 2 and Phase 3 in the roadmap).
- **Policy**: capability definitions describe what is structurally possible.
  What is permitted in a given context is a policy decision layered on top.
