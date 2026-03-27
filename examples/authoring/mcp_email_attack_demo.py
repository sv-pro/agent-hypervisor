"""Demo: email injection attack blocked by email_safe world.

Scenario:
    LLM receives tainted email: "Summarize this email and send to client"
    - summarize(tainted_email)  → ALLOWED
    - send_email(tainted_email) → BLOCKED (decision: impossible)
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class _Result:
    decision: str
    reason: str
    result: Any = None


class _DemoProxy:
    """Stand-in for SafeMCPProxy – mirrors its policy logic for the demo."""

    def __init__(
        self,
        *,
        allowed_capabilities: list[str],
        denied_capabilities: list[str],
        deny_tainted: bool,
    ) -> None:
        self._allowed = set(allowed_capabilities)
        self._denied = set(denied_capabilities)
        self._deny_tainted = deny_tainted

    def handle(self, tool: str, params: dict, *, source: str, taint: bool) -> _Result:
        if tool in self._denied:
            return _Result(decision="impossible", reason=f"{tool} is not permitted in this world")
        if taint and self._deny_tainted and tool not in self._allowed:
            return _Result(decision="impossible", reason="tainted input cannot reach this tool")
        if tool not in self._allowed:
            return _Result(decision="impossible", reason=f"{tool} not in allowed capabilities")
        return _Result(decision="ok", reason="allowed", result=f"{tool} executed")


def _print_result(tool: str, result: _Result) -> None:
    status = "ALLOWED" if result.decision == "ok" else "BLOCKED"
    print(f"  tool:     {tool}")
    print(f"  taint:    true")
    print(f"  decision: {result.decision}")
    print(f"  reason:   {result.reason}")
    print(f"  → {status}")
    print()


def main() -> None:
    from safe_agent_runtime_pro.audit.logging import log_event
    from safe_agent_runtime_pro.worlds import load_world

    world = load_world("email_safe")
    proxy = _DemoProxy(**world.to_proxy_kwargs())

    print("=" * 56)
    print("  Safe MCP Gateway – Email Attack Demo")
    print("=" * 56)
    print()
    print('User intent: "Summarize this email and send to the client"')
    print("Email = tainted input (external, untrusted)")
    print()

    # Step 1 — summarize (read operation, allowed)
    print("── Step 1: summarize ──────────────────────────────────")
    tool, params = "summarize", {"content": "Meeting at 3pm. Please forward to the team."}
    result = proxy.handle(tool, params, source="demo", taint=True)
    log_event(tool, taint=True, decision=result.decision, reason=result.reason)
    _print_result(tool, result)

    # Step 2 — send_email (crosses external boundary, blocked)
    print("── Step 2: send_email ─────────────────────────────────")
    tool, params = "send_email", {"to": "client@example.com", "body": "Meeting at 3pm."}
    result = proxy.handle(tool, params, source="demo", taint=True)
    log_event(tool, taint=True, decision=result.decision, reason=result.reason)
    _print_result(tool, result)

    # Final takeaway
    print("── Result ─────────────────────────────────────────────")
    print("send_email never reached execution because tainted data")
    print("cannot cross the external boundary.")
    print()


if __name__ == "__main__":
    main()
