# Quick Start — Agent Hypervisor

**Time: 5–10 minutes.** You will start the gateway, open the Web UI, observe an attack blocked in real time, and change a manifest rule to see how it affects enforcement.

---

## Prerequisites

- Python 3.10+ or Docker
- No API keys required — the gateway runs fully offline

---

## Step 1 — Start the gateway

### Option A: Docker (recommended)

```bash
docker compose up gateway
```

The gateway starts at **http://localhost:8090/ui**.

### Option B: Local (no Docker)

```bash
pip install -e .

python -c "
import uvicorn
from agent_hypervisor.hypervisor.mcp_gateway.mcp_server import create_mcp_app
from agent_hypervisor.control_plane.api import ControlPlaneState
cp = ControlPlaneState.create()
app = create_mcp_app(
    manifest_path='manifests/example_world.yaml',
    use_default_policy=True,
    control_plane=cp,
)
uvicorn.run(app, host='127.0.0.1', port=8090)
"
```

Open **http://localhost:8090/ui** in your browser.

---

## Step 2 — Observe attack containment

Open the **Benchmarks** tab. You will see `report-v1.md` — a pre-run report from the local scenario suite:

| Metric | Value |
|--------|-------|
| Attack containment rate | 100% |
| False deny rate | 0% |
| Latency overhead | ~0.5 ms |

Nine scenarios were evaluated: 4 attacks (all blocked), 3 safe (all allowed), 2 ambiguous (escalated for approval). The baseline column shows what happens without the hypervisor — attacks succeed.

---

## Step 3 — Inspect a trace

Open the **Traces** tab. Select any session to see its event log — each tool call attempt, the provenance verdict, and the final decision (`ALLOW` / `DENY` / `ASK`).

For an attack trace, you will see:
- Input channel: `email` (untrusted)
- Taint: `True` — propagated from the untrusted source
- Tool attempted: `send_email` with `to: attacker@evil.com`
- Verdict: `DENY` — rule `deny-email-external-recipient` matched

---

## Step 4 — Inspect the provenance rules

Open the **Provenance** tab. This shows the active policy rules loaded from `runtime/configs/default_policy.yaml`. Each rule maps a `(tool, argument, provenance_class)` triple to a verdict.

The rule that blocked the attack:
```yaml
- id: deny-email-external-recipient
  tool: send_email
  argument: to
  provenance: external_document
  verdict: deny
```

This rule is deterministic — no LLM decides whether to apply it. If `to` has `external_document` provenance, `send_email` is denied. Always.

---

## Step 5 — Change the manifest and observe the effect

Open the **Editor** tab. You will see the raw YAML of `manifests/example_world.yaml` — the World Manifest that defines what tools exist in this world.

Try adding a constraint. For example, add a path restriction to `read_file`:

```yaml
capabilities:
  - tool: read_file
    constraints:
      paths: ["/tmp/**"]   # <-- add this line
```

Click **Validate** to check the YAML schema, then **Save**. The gateway hot-reloads the manifest immediately.

Now open the **Simulator** tab and dry-run:
- Tool: `read_file`  
- Args: `{"path": "/etc/passwd"}`
- Provenance: `user_declared`

The simulator evaluates the call against the updated manifest without executing it. With the path constraint, the call is denied. Remove the constraint, save, and re-run — it is allowed.

This is the design→compile→deploy→learn→redesign loop in miniature.

---

## Step 6 — Run the scenario suite (optional)

**From the UI:** Click the **"Run benchmark"** button in the Benchmarks tab. Select a scenario class (all / attack / safe / ambiguous) and click run. Results appear automatically when the run completes.

**From the CLI:**

```bash
# From repo root
PYTHONPATH=src/agent_hypervisor python _research/benchmarks/run_scenarios.py

# Run attack scenarios only
PYTHONPATH=src/agent_hypervisor python _research/benchmarks/run_scenarios.py --class attack
```

Results are written to `_research/benchmarks/reports/`. Reload the Benchmarks tab to see the new report.

---

## Where the guarantees end

The hypervisor enforces **what is in the World Manifest at design time**. It does not handle:

- **Novel attack patterns** not present in the manifest — the manifest covers what was anticipated. New attacks require manifest redesign.
- **Semantic ambiguity** — "forward this to Alex" is not resolved. The semantic gap remains open.
- **Manifest completeness** — a manifest that allows `*` for all tools provides no boundary. Coverage is the designer's responsibility.
- **LLM-generated content safety** — the hypervisor controls what tools the agent can call and with what provenance, not what the LLM says.

The full threat model is in [`docs/architecture/threat-model.md`](architecture/threat-model.md) (if present) or in the [whitepaper](../WHITEPAPER.md).

---

## Next steps

| Goal | Where to look |
|------|--------------|
| Author a manifest for your own agent | `manifests/example_world.yaml` as template; `manifests/schema_v2.yaml` for full schema |
| Run the full AgentDojo benchmark (560 pairs) | `_research/agentdojo-bench/README.md` |
| Understand the architecture | `WHITEPAPER.md` — four-layer model, AI Aikido, World Manifest Compiler |
| See the ZombieAgent scenario | `scenarios/zombie-agent/` |
| Explore the program layer | `docs/program_layer.md` |
