"""
demo.py — Provenance-aware tool execution firewall: runnable MVP demo.

Runs three scenarios against the provenance firewall and prints a readable
summary of each decision. Traces are saved to traces/provenance_firewall/.

Usage:
    python examples/provenance_firewall/demo.py

Three modes:

  A  unprotected / baseline
     The same tool calls execute without any firewall. The malicious
     send_email goes through unchallenged.

  B  protected — malicious recipient blocked
     The firewall is active. The agent proposes send_email with a recipient
     extracted from an external document. The firewall traces the provenance
     chain, finds external_document, and denies the call.

  C  protected — trusted recipient source allowed
     The agent reads from a declared contacts file (user_declared input).
     The recipient traces to a clean provenance chain. The firewall returns
     ask (confirmation required) rather than deny.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make models/policies importable when run from any directory.
HERE = Path(__file__).parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

REPO_ROOT = HERE.parent.parent
TRACES_DIR = REPO_ROOT / "traces" / "provenance_firewall"
MANIFEST_ALLOW = REPO_ROOT / "manifests" / "task_allow_send.yaml"
MANIFEST_DENY  = REPO_ROOT / "manifests" / "task_deny_send.yaml"

from models import Verdict
from policies import ProvenanceFirewall
from agent_sim import scenario_a_unprotected, scenario_b_malicious_blocked, scenario_c_trusted_source


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"


def _verdict_label(v: Verdict) -> str:
    if v == Verdict.allow:
        return f"{GREEN}ALLOW{RESET}"
    if v == Verdict.deny:
        return f"{RED}DENY{RESET}"
    return f"{YELLOW}ASK (confirmation required){RESET}"


def _print_scenario_header(label: str, title: str) -> None:
    print()
    print(f"{BOLD}{'═' * 64}{RESET}")
    print(f"{BOLD}  {label} — {title}{RESET}")
    print(f"{BOLD}{'═' * 64}{RESET}")


def _print_step(tool: str, call_id: str, verdict: Verdict, reason: str,
                violated: list[str], arg_prov: dict[str, str]) -> None:
    print(f"  {DIM}call_id:{RESET} {call_id}")
    print(f"  {DIM}tool:   {RESET} {CYAN}{tool}{RESET}")
    if arg_prov:
        for arg, chain in arg_prov.items():
            print(f"  {DIM}arg [{arg}] provenance:{RESET} {chain}")
    print(f"  {DIM}verdict:{RESET} {_verdict_label(verdict)}")
    print(f"  {DIM}reason: {RESET} {reason}")
    if violated:
        print(f"  {DIM}rules:  {RESET} {', '.join(violated)}")
    print()


# ---------------------------------------------------------------------------
# Trace persistence
# ---------------------------------------------------------------------------

def _save_trace(scenario_id: str, description: str, steps_with_decisions: list) -> Path:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace_path = TRACES_DIR / f"{scenario_id}_{ts}.json"

    trace = {
        "scenario": scenario_id,
        "description": description,
        "timestamp": ts,
        "steps": [],
    }
    for call, registry, decision in steps_with_decisions:
        trace["steps"].append({
            "tool_call": call.to_dict(),
            "decision": decision.to_dict(),
        })

    trace_path.write_text(json.dumps(trace, indent=2))
    return trace_path


# ---------------------------------------------------------------------------
# Scenario runners
# ---------------------------------------------------------------------------

def run_scenario_a() -> list:
    _print_scenario_header("Mode A", "Unprotected baseline — no firewall")
    print("  Task config: (none — protection_enabled=False)")
    print("  Agent behaviour: read malicious doc → extract recipient → send_email")
    print()

    description, steps = scenario_a_unprotected()
    firewall = ProvenanceFirewall(task={}, protection_enabled=False)

    collected = []
    for call, registry in steps:
        decision = firewall.check(call, registry)
        _print_step(call.tool, call.call_id, decision.verdict,
                    decision.reason, decision.violated_rules, decision.arg_provenance)
        collected.append((call, registry, decision))

    print(f"  {BOLD}Outcome:{RESET} Malicious send_email executes — attacker@example.com receives the report.")
    return collected


def run_scenario_b() -> list:
    _print_scenario_header("Mode B", "Protected — malicious recipient blocked")
    print(f"  Task config: manifests/task_deny_send.yaml")
    print(f"  Agent behaviour: read malicious doc → extract recipient → send_email")
    print()

    description, steps = scenario_b_malicious_blocked()
    firewall = ProvenanceFirewall.from_manifest(MANIFEST_DENY, protection_enabled=True)

    collected = []
    for call, registry in steps:
        decision = firewall.check(call, registry)
        _print_step(call.tool, call.call_id, decision.verdict,
                    decision.reason, decision.violated_rules, decision.arg_provenance)
        collected.append((call, registry, decision))

    print(f"  {BOLD}Outcome:{RESET} send_email is denied. Recipient provenance = external_document → RULE-01/02.")
    return collected


def run_scenario_c() -> list:
    _print_scenario_header("Mode C", "Protected — declared contacts source → ask")
    print(f"  Task config: manifests/task_allow_send.yaml")
    print(f"  Agent behaviour: read report + contacts → send_email to approved address")
    print()

    description, steps = scenario_c_trusted_source()
    firewall = ProvenanceFirewall.from_manifest(MANIFEST_ALLOW, protection_enabled=True)

    collected = []
    for call, registry in steps:
        decision = firewall.check(call, registry)
        _print_step(call.tool, call.call_id, decision.verdict,
                    decision.reason, decision.violated_rules, decision.arg_provenance)
        collected.append((call, registry, decision))

    print(f"  {BOLD}Outcome:{RESET} Firewall returns ASK — recipient is clean, but human confirmation required.")
    return collected


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def print_summary(a: list, b: list, c: list) -> None:
    print()
    print(f"{BOLD}{'═' * 64}{RESET}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{BOLD}{'═' * 64}{RESET}")
    print()

    def last_send(steps):
        for call, _, dec in reversed(steps):
            if call.tool == "send_email":
                return dec
        return None

    rows = [
        ("A", "unprotected",                    last_send(a)),
        ("B", "protected / malicious blocked",  last_send(b)),
        ("C", "protected / trusted source",     last_send(c)),
    ]

    fmt = "  {:<4}  {:<35}  {}"
    print(fmt.format("Mode", "Description", "send_email verdict"))
    print("  " + "-" * 60)
    for mode, desc, dec in rows:
        if dec is None:
            verdict_str = "n/a"
        elif dec.verdict == Verdict.allow:
            verdict_str = f"{GREEN}allow{RESET}"
        elif dec.verdict == Verdict.deny:
            verdict_str = f"{RED}deny{RESET}"
        else:
            verdict_str = f"{YELLOW}ask{RESET}"
        print(fmt.format(mode, desc, verdict_str))

    print()
    print("Traces saved to: traces/provenance_firewall/")
    print()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"{BOLD}Agent Hypervisor — Provenance Firewall MVP Demo{RESET}")
    print("Demonstrates provenance-aware tool execution control.")
    print()

    a = run_scenario_a()
    b = run_scenario_b()
    c = run_scenario_c()

    # Save traces
    desc_a, steps_a = scenario_a_unprotected()
    desc_b, steps_b = scenario_b_malicious_blocked()
    desc_c, steps_c = scenario_c_trusted_source()

    fw_none = ProvenanceFirewall(task={}, protection_enabled=False)
    fw_deny = ProvenanceFirewall.from_manifest(MANIFEST_DENY)
    fw_allow = ProvenanceFirewall.from_manifest(MANIFEST_ALLOW)

    _save_trace("mode_a_unprotected",      desc_a,
                [(c, r, fw_none.check(c, r))  for c, r in steps_a])
    _save_trace("mode_b_protected_blocked", desc_b,
                [(c, r, fw_deny.check(c, r))  for c, r in steps_b])
    _save_trace("mode_c_trusted_source",    desc_c,
                [(c, r, fw_allow.check(c, r)) for c, r in steps_c])

    print_summary(a, b, c)


if __name__ == "__main__":
    main()
