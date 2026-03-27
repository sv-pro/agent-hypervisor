"""
Tests for typed denial reasons.

The kernel distinguishes four denial reasons at the type level:
  - NonExistentAction    (action not in the ontology)
  - ConstraintViolation  (trust/capability mismatch)
  - TaintViolation       (tainted data cannot flow here)
  - ApprovalRequired     (approval deferred)

Tests:
  1. NonExistentAction is raised and identifiable by type
  2. ConstraintViolation is raised and identifiable by type
  3. TaintViolation is raised and identifiable by type
  4. ApprovalRequired is raised and identifiable by type
  5. All are subclasses of ConstructionError (backwards compat)
  6. Proxy surfaces denial_kind for each case
  7. Successful execution has no denial_kind
"""

from __future__ import annotations

import os
import pytest

from runtime import (
    build_runtime,
    TaintContext,
    TaintState,
    TaintedValue,
    NonExistentAction,
    ConstraintViolation,
    TaintViolation,
    ApprovalRequired,
    ConstructionError,
)
from runtime.proxy import SafeMCPProxy

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


@pytest.fixture(scope="module")
def rt():
    return build_runtime(MANIFEST)


@pytest.fixture(scope="module")
def proxy(rt):
    return SafeMCPProxy(rt)


# ── 1. NonExistentAction ──────────────────────────────────────────────────────

def test_nonexistent_action_type(rt):
    source = rt.channel("user").source
    exc = None
    try:
        rt.builder.build("not_a_real_action", source, {}, TaintContext.clean())
    except ConstructionError as e:
        exc = e

    assert exc is not None
    assert isinstance(exc, NonExistentAction)
    assert not isinstance(exc, ConstraintViolation)
    assert not isinstance(exc, TaintViolation)
    assert not isinstance(exc, ApprovalRequired)


def test_nonexistent_action_reason_contains_name(rt):
    source = rt.channel("user").source
    with pytest.raises(NonExistentAction) as exc_info:
        rt.builder.build("delete_universe", source, {}, TaintContext.clean())
    assert "delete_universe" in exc_info.value.reason


# ── 2. ConstraintViolation ────────────────────────────────────────────────────

def test_constraint_violation_type(rt):
    # 'external' → UNTRUSTED; send_email is EXTERNAL → capability mismatch
    source = rt.channel("external").source
    exc = None
    try:
        rt.builder.build("send_email", source, {}, TaintContext.clean())
    except ConstructionError as e:
        exc = e

    assert exc is not None
    assert isinstance(exc, ConstraintViolation)
    assert not isinstance(exc, NonExistentAction)
    assert not isinstance(exc, TaintViolation)
    assert not isinstance(exc, ApprovalRequired)


def test_constraint_violation_reason_mentions_trust(rt):
    source = rt.channel("external").source
    with pytest.raises(ConstraintViolation) as exc_info:
        rt.builder.build("send_email", source, {}, TaintContext.clean())
    reason = exc_info.value.reason.lower()
    assert "trust" in reason or "capability" in reason or "untrusted" in reason


# ── 3. TaintViolation ─────────────────────────────────────────────────────────

def test_taint_violation_type(rt):
    # TAINTED + EXTERNAL → TaintViolation
    source = rt.channel("user").source  # trusted — capability check passes first
    tainted_ctx = TaintContext(TaintState.TAINTED)
    exc = None
    try:
        rt.builder.build("post_webhook", source, {}, tainted_ctx)
    except ConstructionError as e:
        exc = e

    assert exc is not None
    assert isinstance(exc, TaintViolation)
    assert not isinstance(exc, NonExistentAction)
    assert not isinstance(exc, ConstraintViolation)
    assert not isinstance(exc, ApprovalRequired)


def test_taint_violation_reason_mentions_taint(rt):
    source = rt.channel("user").source
    tainted_ctx = TaintContext(TaintState.TAINTED)
    with pytest.raises(TaintViolation) as exc_info:
        rt.builder.build("send_email", source, {}, tainted_ctx)
    reason = exc_info.value.reason.lower()
    assert "taint" in reason


def test_tainted_internal_is_not_a_taint_violation(rt):
    """Tainted data + INTERNAL action is allowed — only EXTERNAL triggers TaintViolation."""
    source = rt.channel("user").source
    ctx = TaintContext(TaintState.TAINTED)
    # Should NOT raise:
    ir = rt.builder.build("read_data", source, {}, ctx)
    assert ir.taint is TaintState.TAINTED


# ── 4. ApprovalRequired ───────────────────────────────────────────────────────

def test_approval_required_type(rt):
    source = rt.channel("user").source
    exc = None
    try:
        rt.builder.build("download_report", source, {}, TaintContext.clean())
    except ConstructionError as e:
        exc = e

    assert exc is not None
    assert isinstance(exc, ApprovalRequired)
    assert not isinstance(exc, NonExistentAction)
    assert not isinstance(exc, ConstraintViolation)
    assert not isinstance(exc, TaintViolation)


def test_approval_required_reason_mentions_approval(rt):
    source = rt.channel("user").source
    with pytest.raises(ApprovalRequired) as exc_info:
        rt.builder.build("download_report", source, {}, TaintContext.clean())
    assert "approval" in exc_info.value.reason.lower()


# ── 5. All are ConstructionError subclasses ───────────────────────────────────

def test_all_errors_are_construction_error_subclasses():
    assert issubclass(NonExistentAction, ConstructionError)
    assert issubclass(ConstraintViolation, ConstructionError)
    assert issubclass(TaintViolation, ConstructionError)
    assert issubclass(ApprovalRequired, ConstructionError)


def test_all_errors_are_exceptions():
    assert issubclass(NonExistentAction, Exception)
    assert issubclass(ConstraintViolation, Exception)
    assert issubclass(TaintViolation, Exception)
    assert issubclass(ApprovalRequired, Exception)


# ── 6. Proxy surfaces denial_kind ─────────────────────────────────────────────

def test_proxy_denial_kind_nonexistent(proxy):
    response = proxy.handle({"tool": "not_a_real_tool", "params": {}, "source": "user"})
    assert response.status == "impossible"
    # Tool not in the proxy's tool_map at all
    assert response.denial_kind == "non_existent_action"


def test_proxy_denial_kind_taint_violation(proxy):
    response = proxy.handle({
        "tool": "post_webhook",
        "params": {"url": "https://x.com"},
        "source": "user",
        "taint": True,
    })
    assert response.status == "impossible"
    assert response.denial_kind == "taint_violation"


def test_proxy_denial_kind_constraint_violation(proxy):
    response = proxy.handle({
        "tool": "send_email",
        "params": {},
        "source": "external",
        "taint": False,
    })
    assert response.status == "impossible"
    assert response.denial_kind == "constraint_violation"


def test_proxy_denial_kind_approval_required(proxy):
    response = proxy.handle({
        "tool": "download_report",
        "params": {},
        "source": "user",
        "taint": False,
    })
    assert response.status == "require_approval"
    assert response.denial_kind == "approval_required"


# ── 7. Successful execution has no denial_kind ───────────────────────────────

def test_proxy_success_has_no_denial_kind(proxy):
    response = proxy.handle({
        "tool": "read_data",
        "params": {"query": "test"},
        "source": "user",
        "taint": False,
    })
    assert response.status == "ok"
    assert response.denial_kind is None
