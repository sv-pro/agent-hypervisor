# Module: `runtime/channel.py` — Channel & Source

**Source:** [`src/agent_hypervisor/runtime/channel.py`](../../../src/agent_hypervisor/runtime/channel.py)

This module implements **sealed trust derivation**. Trust level is resolved from the compiled policy map — not from the caller's assertion. Callers provide an *identity string*; the `Channel` resolves the corresponding `TrustLevel`. Unknown identities fail-secure to `UNTRUSTED`.

## Key Types

### `Source` (Sealed)

A trust-bearing identity produced by a `Channel`. It is the trust credential that `IRBuilder.build()` receives.

**Cannot be constructed directly** — attempting `Source(...)` raises `TypeError`. The only way to obtain a `Source` is through `Channel.source` (the property).

**Sealing Mechanism:**
- `Source.__new__` checks for module-private `_SOURCE_SEAL` token
- Only `Channel` holds this token
- External code cannot construct a `Source` without it

**Immutability:** `__setattr__` raises `AttributeError` after construction. Trust level cannot be modified after the `Source` is created.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `trust_level` | `TrustLevel` | Resolved trust (from compiled policy, not caller) |
| `identity` | `str` | The identity string provided by the caller |

**Key Invariant:** Trust is determined by the compiled policy, not by what the caller claims. A caller who passes `identity="admin"` gets whatever trust level the policy assigns to `"admin"` — which may be `UNTRUSTED`.

### `Channel`

Authenticated channel; the only factory for `Source` objects.

**Construction:** `Channel(identity: str, compiled_policy: CompiledPolicy)`

**Immutability:** `__setattr__` raises `AttributeError` after construction.

**Key property:**

| Property | Type | Description |
|---|---|---|
| `source` | `Source` | Returns a sealed `Source` with trust resolved from compiled policy |

**Trust resolution:** `compiled_policy.resolve_trust(identity)` — if identity is not in the trust map, resolves to `UNTRUSTED` (fail-closed).

## Why Sealing Matters

Without sealing, an attacker could fabricate a trusted `Source`:

```python
# Without sealing (hypothetical):
fake_source = Source(trust_level=TrustLevel.TRUSTED, identity="attacker")
ir = builder.build(action, fake_source, params, ctx)
# → bypasses all capability checks
```

With the `_SOURCE_SEAL` pattern, this is impossible. External code cannot construct a `Source` at all.

## Fail-Secure Default

```python
Channel("unknown_identity", policy).source.trust_level
# → TrustLevel.UNTRUSTED  (always, if identity not in trust_map)
```

If the identity is not registered in the compiled trust map, the channel falls back to `UNTRUSTED`. This means:
- New/unrecognized identities cannot accidentally gain elevated trust
- Misconfiguration fails toward restriction, not toward permission

## Usage in the Pipeline

```
Runtime.channel(identity)    → Channel (trust resolved from policy)
    ↓  .source
Source (sealed, immutable trust)
    ↓
IRBuilder.build(action, source, params, taint_ctx)
    ↓  checks source.trust_level against capability matrix
IntentIR (or raises ConstraintViolation)
```

## See Also

- [IR & IRBuilder](ir.md) — receives Source as input; checks trust level
- [Compile Phase](compile.md) — CompiledPolicy.resolve_trust() used by Channel
- [Runtime package](../runtime.md)
- [Trust, Taint, and Provenance](../../concepts/trust-and-taint.md)
