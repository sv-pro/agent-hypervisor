# Practical Workarounds for AI Agent Security

Tactical security patterns you can implement TODAY while Agent Hypervisor matures to production.

---

## Important Disclaimer

These workarounds provide **partial protection** (20–80% depending on implementation and threat model).

They are **not** replacements for architectural security. Each one treats a symptom, not the
root cause (agents inhabiting raw reality).

**Use them to:**

- Get immediate, meaningful protection
- Learn the provenance and taint concepts that underpin Agent Hypervisor
- Build a migration path toward full architectural enforcement

**Do not rely on them for:**

- High-stakes production without additional layers
- Protection against adaptive adversaries who probe defenses
- Complete security guarantees

---

## Workaround 1: Input Classification

**Implementation time:** 30 minutes
**Protection level:** 20–30%
**Concept:** Tag every input with its source and trust level at ingestion time.

### The problem it addresses

Agents process all text identically — a system prompt and a malicious email get the same
treatment. The agent cannot structurally distinguish them.

### What it does

Wraps raw inputs in a structured envelope that carries provenance metadata:

```python
{
    "content": "<original data>",
    "source": "external_email",
    "trust_level": "UNTRUSTED",
    "capabilities": {"can_write": False, "can_send_external": False}
}
```

### How to implement

See [`examples/workarounds/01_input_classification.py`](../examples/workarounds/01_input_classification.py).

### Limitations

- Tags data but does not enforce boundaries — you must check `trust_level` everywhere
- Discipline-dependent: a missed check anywhere breaks the model
- No propagation: if untrusted data is copied into a trusted context, the tag is lost

### Migration to Agent Hypervisor

This classification becomes automatic at the Virtualization Boundary. The Hypervisor tags
all inputs as Semantic Events and propagates trust through data flows deterministically.

---

## Workaround 2: Memory Provenance Tracking

**Implementation time:** 4 hours
**Protection level:** 40–50% + forensic capability
**Concept:** Record the source of every memory write.

### The problem it addresses

ZombieAgent (Radware, Jan 2026): an agent's long-term memory was poisoned because memory
writes carried no origin information. After poisoning, the agent behaved as instructed by
the attacker — with no evidence of when or how the compromise occurred.

### What it does

Wraps the memory store so every `write` records where the data came from:

```python
memory.write("instructions", value="...", provenance="external_email:sender@attacker.com")
```

On read, provenance is available:

```python
entry = memory.read("instructions")
entry["provenance"]  # → "external_email:sender@attacker.com"
entry["trust_level"]  # → "UNTRUSTED"
```

### How to implement

See [`examples/workarounds/02_memory_provenance.py`](../examples/workarounds/02_memory_provenance.py).

### Limitations

- Forensic, not preventive: you can see *that* poisoning occurred, but not stop it
- Must be applied to every write path — missed paths are unprotected
- Does not propagate through transformations (if untrusted data is summarized and stored, the
  summary may not carry the original provenance)

### Migration to Agent Hypervisor

The Hypervisor's Provenance Law makes this automatic and structural: untrusted-tainted data
cannot write to execution memory. No discipline required — it is a physics law.

---

## Workaround 3: Read-Only Tool Wrappers

**Implementation time:** 15 minutes per tool
**Protection level:** Prevents accidental side effects (not intentional attacks)
**Concept:** Wrap tools to make them read-only during development and testing.

### The problem it addresses

During development, agents with write-capable tools can accidentally (or under injection)
modify files, send emails, or call external APIs. Read-only wrappers eliminate the accident
surface entirely during non-production phases.

### What it does

Intercepts tool calls and blocks any that would cause side effects:

```python
safe_tool = ReadOnlyWrapper(write_file_tool)
safe_tool.execute(path="output.txt", content="...")
# → raises ReadOnlyViolation: "write_file is not permitted in read-only mode"
```

### How to implement

See [`examples/workarounds/03_readonly_tools.py`](../examples/workarounds/03_readonly_tools.py).

### Limitations

- For development/testing only — must be removed or replaced in production
- Does not handle attacks that abuse read-only tools (e.g., exfiltration via GET requests)

### Migration to Agent Hypervisor

The Hypervisor's tool whitelist and Reversibility Law provide production-grade equivalents:
only staged, approved intents are materialized, and side effects are committed only after
explicit confirmation.

---

## Workaround 4: Segregated Memory

**Implementation time:** 4 hours
**Protection level:** 60–70%
**Concept:** Separate agent memory into trust-level zones — trusted instructions cannot be
overwritten by untrusted inputs.

### The problem it addresses

When continuous learning arrives (Dario Amodei, Feb 2026: "1–2 years"), agents will update
their own behavior from experience. If untrusted inputs can write to the learning store, a
single poisoned interaction permanently corrupts the agent's behavior.

Segregated memory limits the blast radius: untrusted data can only write to its own zone.

### What it does

```python
memory = SegregatedMemory()
memory.write("system_config", value="...", trust_zone="TRUSTED")   # OK
memory.write("user_note",     value="...", trust_zone="UNTRUSTED") # OK
memory.write("system_config", value="...", trust_zone="UNTRUSTED") # BLOCKED
```

### How to implement

See [`examples/workarounds/04_segregated_memory.py`](../examples/workarounds/04_segregated_memory.py).

### Limitations

- Requires defining zone boundaries correctly — subtle misclassifications break protection
- Cross-zone reads (reading untrusted data into a trusted context) can still leak influence
- Does not prevent read-based attacks (agent reads untrusted data and is influenced by it)

### Migration to Agent Hypervisor

Trust zones become Universe boundaries enforced as physics laws. The Provenance Law prevents
untrusted data from influencing execution memory regardless of how the agent reads it.

---

## Workaround 5: Taint Tracking

**Implementation time:** 1 day
**Protection level:** 50–60%
**Concept:** Attach a `taint` label to untrusted data and propagate it through transformations,
blocking the data from crossing external boundaries.

### The problem it addresses

ShadowLeak (Radware, 2025): a crafted email caused an agent to exfiltrate the user's Gmail
inbox. The attack worked because the agent processed email content without tracking that
the resulting actions were derived from untrusted input.

### What it does

```python
data = taint_tracker.tag(email_body, taint="UNTRUSTED")
summary = agent.summarize(data)           # summary inherits taint
taint_tracker.check_boundary(summary)    # raises TaintViolation before send
```

### How to implement

See [`examples/workarounds/05_taint_tracking.py`](../examples/workarounds/05_taint_tracking.py).

### Limitations

- Manual propagation through all code paths — any gap breaks containment
- Does not handle implicit flows (statistical or semantic influence without direct data copy)
- High implementation complexity; easy to introduce subtle bugs

### Migration to Agent Hypervisor

The Hypervisor's Taint Containment Law enforces this deterministically at the boundary.
Taint propagation is built into the Semantic Event model — no manual tracking needed.

---

## Workaround 6: Audit Logging

**Implementation time:** 1 day
**Protection level:** Reactive (forensics and compliance, not prevention)
**Concept:** Record an immutable, append-only log of every agent action with its provenance.

### The problem it addresses

After a ZombieAgent-style attack, there is typically no record of when the memory was
poisoned, what instruction triggered it, or what data was accessed. Audit logging provides
the evidence trail needed for incident response and compliance.

### What it does

```python
audit.log(
    action="memory_write",
    key="agent_instructions",
    source="external_email",
    trust_level="UNTRUSTED",
    result="written",
    timestamp="2026-02-14T10:23:41Z"
)
```

### How to implement

See [`examples/workarounds/06_audit_logging.py`](../examples/workarounds/06_audit_logging.py).

### Limitations

- Reactive only: records attacks, does not prevent them
- Requires log integrity protection (otherwise an attacker deletes the log)
- Useful for compliance and post-incident analysis, not real-time defense

### Migration to Agent Hypervisor

The Hypervisor's event log provides this automatically, with provenance guaranteed by
the virtualization boundary. Every Semantic Event and Intent decision is recorded.

---

## Combining Workarounds

Maximum protection stack (approximately 75–80% against basic, non-adaptive attacks):

```python
# Layer 1: Classify input at ingestion
classified = input_classifier.classify(raw_input, source="external_email")

# Layer 2: Tag with taint
tainted_data = taint_tracker.tag(classified["content"], taint=classified["trust_level"])

# Layer 3: Write to segregated memory with provenance
memory.write("context", tainted_data, trust_zone=classified["trust_level"],
             provenance=classified["source"])

# Layer 4: Check boundary before any external action
taint_tracker.check_boundary(output_data)

# Layer 5: Audit log everything
audit.log(action="process_email", source=classified["source"],
          trust_level=classified["trust_level"])
```

**Still vulnerable to:**

- Adaptive attackers who probe and learn from defense reactions
- Novel exploitation techniques not covered by tagging heuristics
- Continuous learning contamination (without careful zone boundaries)
- Implicit semantic influence (LLM influenced by untrusted data it reads, even without
  direct data propagation)

---

## Recommended Implementation Order

### Week 1: Foundation (< 2 hours total)

1. `01_input_classification.py` — 30 minutes — establishes provenance vocabulary
2. `03_readonly_tools.py` — 15 min per tool — eliminates accidental write surface
3. `06_audit_logging.py` — full day — enables incident forensics

### Week 2: Core Protection (1 day)

4. `04_segregated_memory.py` — half day — prevents cross-trust writes
5. `02_memory_provenance.py` — half day — adds forensic detail to memory

### Week 3: Advanced (optional, 1 day)

6. `05_taint_tracking.py` — full day — adds data-flow boundary enforcement

---

## Workaround-to-Hypervisor Migration Map

| Workaround | Agent Hypervisor Equivalent |
| --- | --- |
| Input classification | Semantic Event virtualization |
| Memory provenance | Provenance Law (built-in) |
| Read-only tools | Reversibility Law + staging |
| Segregated memory | Universe trust-zone boundaries |
| Taint tracking | Taint Containment Law (deterministic) |
| Audit logging | Event log + provenance chain |

---

*See [`examples/workarounds/`](../examples/workarounds/) for runnable implementations of each pattern.*
