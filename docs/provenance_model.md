# Provenance Model

Provenance is the record of where a value came from and how it was transformed
before it reached the tool execution boundary.

In Agent Hypervisor, provenance is not metadata attached to a value as an
afterthought. It is a first-class property of every value the agent works with,
enforced structurally at evaluation time.

---

## ValueRef

Every value in the system is wrapped in a `ValueRef`:

```python
@dataclass
class ValueRef:
    id: str                         # unique identifier for this value
    value: Any                      # the actual value (string, list, etc.)
    provenance: ProvenanceClass     # where it ultimately came from
    roles: list[Role]               # intended use in the current task
    parents: list[str]              # ids of ValueRefs this was derived from
    source_label: str               # human-readable origin description
```

The agent never works with raw strings for values that will be used in tool
arguments. Every such value is a `ValueRef`.

---

## Provenance Classes

Ordered from least trusted to most trusted:

| Class               | Meaning                                                  | Trust  |
|---------------------|----------------------------------------------------------|--------|
| `external_document` | Content from files, emails, web pages, API responses     | Lowest |
| `derived`           | Computed or extracted from one or more parent values     | —      |
| `user_declared`     | Explicitly declared by the operator in the task manifest | High   |
| `system`            | Hardcoded by the system — no user influence possible     | Highest|

**Key invariant:** provenance can only flow from less trusted to more trusted
through *explicit operator declaration*, not through computation.

---

## Roles

Roles describe the *semantic purpose* of a value within the current task:

| Role                  | Meaning                                      |
|-----------------------|----------------------------------------------|
| `recipient_source`    | This value names email recipients            |
| `extracted_recipients`| Email addresses extracted from a document    |
| `report_source`       | A document being summarised                  |
| `data_source`         | Raw data being processed                     |
| `generated_report`    | The agent's own output                       |

Roles are used in RULE-02: the `to` argument of `send_email` must trace to an
ancestor with `role=recipient_source` and `provenance=user_declared`.

---

## Parent Relationships

When a value is derived from other values, the derived `ValueRef` records the
parent ids:

```
contacts.txt (user_declared, role=recipient_source)
    id: "declared:approved_contacts"
         │
         ▼
email address extracted from contacts
    id: "extracted:contact:0:declared:approved_contacts"
    provenance: derived
    parents: ["declared:approved_contacts"]
    roles: [extracted_recipients]
```

This forms a **directed acyclic graph (DAG)** of derivations. The firewall walks
this DAG at evaluation time using `resolve_chain()`.

---

## Provenance Chains

`resolve_chain(ref, registry)` returns all ancestors of a `ValueRef`, including
itself, in BFS order:

```python
chain = resolve_chain(recipient_ref, registry)
# → [recipient_ref (derived), contacts_ref (user_declared)]
```

The chain is used to:

1. **Detect untrusted ancestry** — does any ancestor have `external_document`?
2. **Find declared sources** — does any ancestor have `user_declared` with the
   required role?
3. **Compute effective trust** — the least-trusted ancestor dominates (RULE-03).

---

## Mixed Provenance

A value has mixed provenance when its chain contains ancestors from more than one
provenance class. This is detected by `mixed_provenance(ref, registry)`:

```python
mixed_provenance(ref, registry)
# → True if len({v.provenance for v in chain}) > 1
```

### Why mixed provenance matters

Mixed provenance is a signal that a value's ancestry includes sources of different
trust levels. The less-trusted source always dominates (RULE-03), but the presence
of a trusted ancestor could falsely imply legitimacy.

**Example (recipient laundering attempt):**

```
attacker embeds address in document
    doc_ref (external_document)
         │
         ▼
agent extracts address
    addr_extracted (derived, parents=[doc_ref])

operator declares contacts file
    contacts_ref (user_declared, role=recipient_source)
         │
         ▼
combined address (derived, parents=[addr_extracted, contacts_ref])
    ← mixed provenance: external_document + user_declared
    ← least trusted = external_document
    ← RULE-01 fires → deny
```

Even though `contacts_ref` is trusted, the `external_document` ancestor
dominates. The combination does not produce a trusted value.

---

## Sticky Provenance (RULE-03)

> A derived value inherits the least-trusted provenance class among its parents.
> Wrapping an external value does not launder it.

This is the core anti-laundering invariant. It means:

- Reading a malicious document and extracting text from it → the extracted text
  is `derived` with `external_document` in its ancestry.
- Combining that extracted text with a trusted value → the combination is
  `derived` with `external_document` in its ancestry.
- Creating a new `ValueRef` that claims `user_declared` provenance for a value
  that was actually derived from an external document → the chain still contains
  the `external_document` ancestor.

The firewall always walks the full chain. Provenance claims on the leaf node
alone are not sufficient.

---

## Trace Output

When the firewall evaluates a tool call, it logs the provenance summary for each
argument:

```
tool: send_email
arg [to] provenance: derived:extracted from malicious_doc.txt <- external_document:malicious_doc.txt
verdict: deny
reason: Recipient provenance traces to external_document — external documents cannot authorize outbound email
rules: RULE-01, RULE-02
```

This format — `current_class:label <- parent_class:label <- …` — shows the full
derivation path for each argument and makes it immediately clear why a decision
was made.
