# Basic Examples

Core demonstrations of Agent Hypervisor functionality.

---

## 01_simple_demo.py

Runs seven scenarios through the Hypervisor, illustrating all three physics layers.

**Run:**

```bash
python examples/basic/01_simple_demo.py
```

**What it demonstrates:**

- Layer 1 — Forbidden patterns: dangerous argument strings are globally blocked
- Layer 2 — Tool whitelist: only tools that exist in this world can be used
- Layer 3 — State limits: cumulative session constraints are enforced

**Key concepts:**

- Intent Proposals — agents propose, never execute directly
- Deterministic Policy — same intent + policy always gives same decision
- Ontological boundary — unknown tools don't exist, they aren't merely forbidden

**Next steps:**

- Read [docs/HELLO_WORLD.md](../../docs/HELLO_WORLD.md) for a detailed walkthrough
- Modify [config/policy.yaml](../../config/policy.yaml) to see different behaviors
- Review [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for the full technical spec
