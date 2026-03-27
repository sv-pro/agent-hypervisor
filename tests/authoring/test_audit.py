"""Tests for audit/logging."""

import json

from safe_agent_runtime_pro.audit.logging import log_event


def test_log_event_emits_json(capsys):
    log_event("read_data", False, "ok", "allowed")
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["tool"] == "read_data"
    assert payload["decision"] == "ok"
    assert payload["taint"] is False
    assert "timestamp" in payload


def test_log_event_blocked(capsys):
    log_event("send_email", True, "impossible", "blocked by policy")
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["decision"] == "impossible"
    assert payload["taint"] is True
