# Practical Workarounds

Tactical security patterns you can implement TODAY while Agent Hypervisor matures.

> **Important:** These provide partial protection (20–80%). They are not replacements for
> architectural security. See [docs/WORKAROUNDS.md](../../docs/WORKAROUNDS.md) for full details.

---

## Quick Wins (< 1 hour)

### [01_input_classification.py](01_input_classification.py)

**Time:** 30 min | **Protection:** 20–30% | **Concept:** Tag inputs with source and trust level

Foundation for all other workarounds. Establishes the provenance vocabulary.

```bash
python 01_input_classification.py
```

### [03_readonly_tools.py](03_readonly_tools.py)

**Time:** 15 min per tool | **Protection:** Prevents accidents | **Concept:** Wrap tools read-only

Eliminates accidental side-effects during development and testing.

```bash
python 03_readonly_tools.py
```

---

## Half-Day Projects (2–4 hours)

### [02_memory_provenance.py](02_memory_provenance.py)

**Time:** 4 hours | **Protection:** 40–50% + forensics | **Concept:** Track the source of every memory write

Addresses ZombieAgent-style attacks. Provides forensic trail even when prevention fails.

```bash
python 02_memory_provenance.py
```

### [04_segregated_memory.py](04_segregated_memory.py)

**Time:** 4 hours | **Protection:** 60–70% | **Concept:** Separate memory by trust zone

Critical for continuous learning. Prevents untrusted inputs from overwriting trusted state.

```bash
python 04_segregated_memory.py
```

---

## Full-Day Projects

### [05_taint_tracking.py](05_taint_tracking.py)

**Time:** 1 day | **Protection:** 50–60% | **Concept:** Track data contamination through transformations

Addresses ShadowLeak-style exfiltration. Most complex workaround to implement correctly.

```bash
python 05_taint_tracking.py
```

### [06_audit_logging.py](06_audit_logging.py)

**Time:** 1 day | **Protection:** Reactive (forensics) | **Concept:** Immutable action log

Provides evidence trail for incident response and compliance. Does not prevent attacks.

```bash
python 06_audit_logging.py
```

---

## Recommended Order

**Week 1:** `01` → `03` → `06`
**Week 2:** `04` → `02`
**Week 3 (optional):** `05`

---

## Migration to Agent Hypervisor

| Workaround | Agent Hypervisor Equivalent |
| --- | --- |
| Input classification | Semantic Event virtualization |
| Memory provenance | Provenance Law (built-in) |
| Read-only tools | Reversibility Law + staging |
| Segregated memory | Universe trust-zone boundaries |
| Taint tracking | Taint Containment Law (deterministic) |
| Audit logging | Event log + provenance chain |

See [docs/WORKAROUNDS.md](../../docs/WORKAROUNDS.md) for full documentation.
