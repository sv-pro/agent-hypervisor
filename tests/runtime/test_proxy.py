"""
Proxy Tests
===========

Focused tests for the Safe MCP Proxy layer.

Invariants verified:
  1. Unknown tool never reaches the worker
  2. Tainted external tool never reaches the worker
  3. Allowed internal tool reaches the worker and returns a result
  4. Proxy does not execute tools directly (no handler functions)
  5. Proxy output is structured and stable
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from runtime import build_runtime
from runtime.proxy import SafeMCPProxy, DEFAULT_TOOL_MAP
from runtime.protocol import ToolRequest, ProxyResponse


@pytest.fixture
def proxy():
    rt = build_runtime()
    return SafeMCPProxy(rt)


# ── 1. Unknown tool never reaches the worker ─────────────────────────────────

def test_unknown_tool_returns_impossible(proxy):
    """Unknown tool name returns impossible before any runtime construction."""
    response = proxy.handle({
        "tool": "delete_repository",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert response.status == "impossible"
    assert "does not exist in this world" in response.reason


def test_unknown_tool_worker_never_called(proxy):
    """Worker subprocess is never spawned for an unknown tool."""
    with patch("runtime.executor.subprocess.run") as mock_run:
        proxy.handle({
            "tool": "launch_missile",
            "params": {},
            "source": "user",
            "taint": False,
        })
        mock_run.assert_not_called()


def test_unknown_tool_has_no_action_in_response(proxy):
    """Response for an unknown tool has no action field."""
    response = proxy.handle({
        "tool": "hack_the_planet",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert response.status == "impossible"
    assert response.action is None
    assert response.result is None


# ── 2. Tainted external tool never reaches the worker ────────────────────────

def test_tainted_send_email_is_impossible(proxy):
    """Tainted send_email (external action) is blocked at IR construction."""
    response = proxy.handle({
        "tool": "send_email",
        "params": {"to": "client", "body": "hello"},
        "source": "user",
        "taint": True,
    })
    assert response.status == "impossible"
    assert response.action == "send_email"


def test_tainted_send_email_worker_never_called(proxy):
    """Worker is never called when tainted data targets an external action."""
    with patch("runtime.executor.subprocess.run") as mock_run:
        proxy.handle({
            "tool": "send_email",
            "params": {"to": "client"},
            "source": "user",
            "taint": True,
        })
        mock_run.assert_not_called()


def test_tainted_post_webhook_worker_never_called(proxy):
    """Same taint containment for post_webhook (also external)."""
    with patch("runtime.executor.subprocess.run") as mock_run:
        proxy.handle({
            "tool": "post_webhook",
            "params": {"url": "http://example.com"},
            "source": "user",
            "taint": True,
        })
        mock_run.assert_not_called()


# ── 3. Allowed internal tool reaches the worker ───────────────────────────────

def test_clean_internal_tool_succeeds(proxy):
    """Clean read_data (internal) succeeds end-to-end through the worker."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert response.status == "ok"
    assert response.action == "read_data"
    assert response.result is not None


def test_tainted_internal_tool_reaches_worker(proxy):
    """Tainted internal action is not blocked — taint rule only fires for external."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": True,
    })
    assert response.status == "ok"
    assert response.action == "read_data"


def test_allowed_tool_result_is_dict(proxy):
    """Worker result is a dict wrapped in the ProxyResponse."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert isinstance(response.result, dict)


# ── 4. Proxy does not execute tools directly ─────────────────────────────────

def test_proxy_has_no_handler_registry():
    """SafeMCPProxy holds no callable action handlers — no _handlers dict."""
    rt = build_runtime()
    proxy = SafeMCPProxy(rt)
    assert not hasattr(proxy, "_handlers")
    assert not hasattr(proxy, "handlers")


def test_proxy_internal_state_is_runtime_and_map():
    """Proxy internals are only a runtime reference and an explicit tool map."""
    rt = build_runtime()
    proxy = SafeMCPProxy(rt)
    assert proxy._runtime is rt
    assert isinstance(proxy._tool_map, dict)


def test_default_tool_map_is_explicit():
    """Default tool map is explicitly declared — not derived from tool names at runtime."""
    for tool_name, action_name in DEFAULT_TOOL_MAP.items():
        assert isinstance(tool_name, str)
        assert isinstance(action_name, str)
    assert len(DEFAULT_TOOL_MAP) > 0


def test_proxy_with_custom_tool_map():
    """Proxy accepts a custom tool map — mapping is not hardcoded."""
    rt = build_runtime()
    custom_map = {"my_reader": "read_data"}
    proxy = SafeMCPProxy(rt, tool_map=custom_map)

    response = proxy.handle({
        "tool": "my_reader",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert response.status == "ok"
    assert response.action == "read_data"


# ── 5. Proxy output is structured and stable ─────────────────────────────────

def test_response_is_proxy_response_type(proxy):
    """handle() always returns a ProxyResponse, never raises."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert isinstance(response, ProxyResponse)


def test_impossible_response_has_reason(proxy):
    """Impossible responses always carry a reason string."""
    response = proxy.handle({
        "tool": "nonexistent",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert response.status == "impossible"
    assert response.reason is not None
    assert len(response.reason) > 0


def test_ok_response_has_action_and_result(proxy):
    """Successful responses carry both action name and result dict."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert response.status == "ok"
    assert response.action is not None
    assert response.result is not None


def test_to_dict_ok_is_stable(proxy):
    """to_dict() on an ok response is stable and complete."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })
    d = response.to_dict()
    assert d["status"] == "ok"
    assert "action" in d
    assert "result" in d
    assert "reason" not in d


def test_to_dict_impossible_is_stable(proxy):
    """to_dict() on an impossible response is stable and complete."""
    response = proxy.handle({
        "tool": "delete_repository",
        "params": {},
        "source": "user",
        "taint": False,
    })
    d = response.to_dict()
    assert d["status"] == "impossible"
    assert "reason" in d
    assert "result" not in d


def test_accepts_tool_request_object(proxy):
    """Proxy accepts ToolRequest objects as well as dicts."""
    req = ToolRequest(tool="read_data", params={}, source="user", taint=False)
    response = proxy.handle(req)
    assert response.status == "ok"
