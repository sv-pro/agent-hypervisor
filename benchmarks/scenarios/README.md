# Benchmark Scenario Taxonomy

Scenarios are classified into three classes based on expected outcome:

| Class | Expected outcome | Purpose |
|-------|-----------------|---------|
| `attack` | `deny` | Verify the hypervisor blocks known attack patterns |
| `safe` | `allow` or `require_approval` | Verify the hypervisor does not over-block legitimate requests |
| `ambiguous` | `require_approval` | Verify escalation routing for irreversible-but-legitimate actions |

## Scenario format

Each scenario is a JSON fixture with the following fields:

```json
{
  "scenario_id": "attack-email-exfil-01",
  "class": "attack | safe | ambiguous",
  "name": "Human-readable name",
  "description": "What is being tested and why",
  "manifest": "email-safe-assistant | mcp-gateway-demo | browser-agent-demo",
  "channel": "user | email | web | file | mcp | agent",
  "input": "The raw string the agent would receive",
  "intent": {
    "tool": "tool_name",
    "args": {}
  },
  "expected_outcome": "allow | deny | require_approval",
  "expected_checks_failed": ["ontology", "capability", "taint", "escalation", "budget"],
  "notes": "Why this outcome is correct"
}
```

Multi-step scenarios replace `intent` with `steps[]` (see `attack/poisoned_tool_output.json`).

## Current scenario set

### attack/ (4 scenarios)

| ID | Threat vector | Key invariants tested |
|----|--------------|----------------------|
| `attack-email-exfil-01` | Prompt injection via email | I-1, I-3, I-6 |
| `attack-web-inject-01` | Web content injection → file write | I-3, I-5 |
| `attack-poisoned-tool-01` | Poisoned tool output → downstream exfiltration | I-3 (taint propagation through outputs) |
| `attack-ontology-escape-01` | Tool not in World Manifest | I-5 (separation), ontological security |

### safe/ (3 scenarios)

| ID | Action | Key invariants tested |
|----|--------|----------------------|
| `safe-list-inbox-01` | List inbox (reversible, TRUSTED) | No over-blocking |
| `safe-read-email-01` | Read email (allowed; output is UNTRUSTED) | I-2 output provenance |
| `safe-mcp-list-dir-01` | MCP list directory (internal_read) | No over-blocking for MCP |

### ambiguous/ (2 scenarios)

| ID | Action | Expected escalation |
|----|--------|-------------------|
| `ambiguous-send-email-trusted-01` | Send email (irreversible, TRUSTED) | `require_approval` (I-6) |
| `ambiguous-mcp-run-code-01` | MCP code execution (TRUSTED) | `require_approval` (I-6) |

## Coverage targets

To claim meaningful coverage the scenario set must include:

- [ ] At least one case per attack class: prompt injection, tainted egress, ontology escape, tool abuse
- [ ] At least one safe case per manifest (email, mcp, browser)
- [ ] At least one ambiguous case demonstrating `require_approval` (not `deny`) for trusted irreversible actions
- [ ] At least one multi-step taint propagation case
