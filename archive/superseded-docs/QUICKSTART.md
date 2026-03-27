# Quickstart — Agent Hypervisor

First useful result in 5–10 minutes. You will:

1. Install the package
2. Run the three-scenario demo
3. Change a manifest rule and see physics change
4. Run the benchmark and view the metrics report

---

## Prerequisites

- Python 3.10+
- Git

---

## Step 1 — Install

```bash
git clone https://github.com/sv-pro/agent-hypervisor
cd agent-hypervisor
pip install -e .
```

---

## Step 2 — Run the demo

```bash
python examples/basic/02_hypervisor_demo.py
```

You will see three annotated scenarios:

- **Scenario A** — Email injection attack: raw input is sanitized, intent is denied at the capability check.
- **Scenario B** — Poisoned tool output: MCP output propagates taint; downstream write is blocked.
- **Scenario C** — Legitimate user workflow: list_inbox is allowed; send_email is escalated (not denied).

The demo prints the full reason chain for each decision. Read it line by line to see exactly where each attack loses effect.

---

## Step 3 — Change a manifest rule and rebuild

Open `manifests/examples/email-safe-assistant.yaml`. Find the `capability_matrix` section:

```yaml
capability_matrix:
  TRUSTED:
    - external_write
    - external_read
  ...
```

Remove `external_read` from `TRUSTED`:

```yaml
capability_matrix:
  TRUSTED:
    - external_write
  ...
```

Rebuild the compiled artifacts:

```bash
ahc build manifests/examples/email-safe-assistant.yaml -o manifests/examples/compiled/email-safe-assistant
```

Re-run the demo. Scenario C will now show `list_inbox` **denied** at the capability check, because TRUSTED can no longer external_read.

Restore the original rule and rebuild to return to the working state.

**What this demonstrates:** The World Manifest is the only place where the physics of the agent's world are defined. Changing a YAML rule changes runtime behavior — no code change required.

---

## Step 4 — Run the benchmark

```bash
python benchmarks/runner.py
python benchmarks/metrics.py --output benchmarks/reports/report-v1.md
cat benchmarks/reports/report-v1.md
```

The report shows:

| Metric | Value |
|--------|-------|
| Attack containment rate | 100% |
| False deny rate | 0% |
| Task completion rate | 100% |
| Latency overhead | < 1 ms |

---

## Step 5 — Replay a trace

```bash
python benchmarks/replay.py --walkthrough
```

This replays the latest benchmark trace and prints the policy reason chain for each scenario. Every outcome is deterministic — the same input always produces the same decision.

---

## Step 6 — Run with Docker

```bash
docker compose up demo        # three-scenario demo
docker compose up benchmarks  # full benchmark + report
```

---

## What to read next

- [CONCEPT.md](../CONCEPT.md) — How the hypervisor works (10 min read)
- [manifests/schema.yaml](../manifests/schema.yaml) — World Manifest reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — Five-layer design
- [VERIFICATION_PLAN.md](../VERIFICATION_PLAN.md) — DOD checklist for all issues
- [benchmarks/reports/report-v1.md](../benchmarks/reports/report-v1.md) — Current benchmark results
