"""
tests/test_policy.py — Unit tests for the Hypervisor's deterministic policy evaluation.

These tests verify that the Hypervisor enforces the World Policy correctly.
They also serve as usage examples: each test shows the exact intent dict format
and the expected decision structure.

Design principle: every safety property of the hypervisor must be expressible
as a deterministic unit test. If a rule cannot be tested this way, it belongs
in a probabilistic guardrail, not in a hypervisor physics law.

Run with:
    pytest
"""

import pytest
from hypervisor import Hypervisor


@pytest.fixture
def hv() -> Hypervisor:
    """
    Provide a fresh Hypervisor instance for each test.

    A new instance resets WorldState, ensuring that state-dependent tests
    (e.g., max_files_opened) are not affected by execution order.
    """
    return Hypervisor("policy.yaml")


# ---------------------------------------------------------------------------
# Layer 2: Tool whitelist
# ---------------------------------------------------------------------------

def test_allowed_tool(hv: Hypervisor) -> None:
    """An intent using a whitelisted tool with safe args is approved."""
    intent = {"tool": "read_file", "args": "valid_file.txt"}
    result = hv.evaluate(intent)
    assert result["status"] == "ALLOWED"


def test_unknown_tool_is_blocked(hv: Hypervisor) -> None:
    """
    An intent using a tool not in allowed_tools is blocked.

    The tool 'format_disk' is not dangerous per se — it simply does not
    exist in this world. The distinction matters: blocked because unknown,
    not because forbidden.
    """
    intent = {"tool": "format_disk", "args": "/dev/sda"}
    result = hv.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "not in allowed_tools" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Layer 1: Forbidden patterns
# ---------------------------------------------------------------------------

def test_forbidden_pattern_rm_rf(hv: Hypervisor) -> None:
    """
    An intent whose args contain 'rm -rf' is blocked at the pattern layer,
    before the tool whitelist is even checked. This ensures the pattern
    layer catches dangerous arguments regardless of what tool is named.
    """
    intent = {"tool": "execute_shell", "args": "rm -rf /"}
    result = hv.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "forbidden pattern" in result["reason"].lower()


def test_forbidden_pattern_api_key_export(hv: Hypervisor) -> None:
    """
    An intent whose args contain 'api_key_export' is blocked.

    This prevents a common exfiltration pattern where a prompt-injected agent
    is instructed to echo secrets into a file named after the forbidden keyword.
    """
    intent = {"tool": "execute_shell", "args": "echo $API_KEY > api_key_export"}
    result = hv.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "forbidden pattern" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Layer 3: State limits
# ---------------------------------------------------------------------------

def test_state_limit_enforcement(hv: Hypervisor) -> None:
    """
    The max_files_opened limit (3) is enforced cumulatively across a session.

    The first three read_file intents are approved; the fourth is blocked
    regardless of the file name. This models a physics law: after N file reads,
    the action 'read_file' ceases to be available in this world session.
    """
    # Open 3 files — all should be allowed
    for i in range(3):
        intent = {"tool": "read_file", "args": f"file_{i}.txt"}
        result = hv.evaluate(intent)
        assert result["status"] == "ALLOWED", f"File {i} should be allowed"

    # Fourth attempt — should be blocked by the state limit
    intent = {"tool": "read_file", "args": "file_overflow.txt"}
    result = hv.evaluate(intent)
    assert result["status"] == "BLOCKED"
    assert "state limit reached" in result["reason"].lower()
