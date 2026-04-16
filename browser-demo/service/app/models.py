"""
Pydantic models for all API request/response types.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inbound: page event
# ---------------------------------------------------------------------------

class PageEvent(BaseModel):
    source_type: str = "web_page"
    url: str
    title: str
    visible_text: str = ""
    hidden_content_detected: bool = False
    hidden_content_summary: Optional[str] = None
    content_hash: str = ""
    captured_at: str = ""


class IngestResponse(BaseModel):
    event_id: str
    trust: str          # "trusted" | "untrusted"
    taint: bool
    available_actions: list[str]
    message: str = ""


# ---------------------------------------------------------------------------
# Inbound: intent evaluation
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    event_id: str
    intent_type: str    # "summarize_page" | "extract_links" | …
    params: dict[str, Any] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    decision: str       # "allow" | "deny" | "ask" | "simulate"
    rule_hit: str
    reason: str
    trace_id: str


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

class ApprovalRequest(BaseModel):
    trace_id: str
    approved: bool
    note: str = ""


class ApprovalResponse(BaseModel):
    trace_id: str
    final_decision: str
    message: str


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------

class TraceEntry(BaseModel):
    trace_id: str
    event_id: str
    intent_type: str
    trust: str
    taint: bool
    decision: str
    rule_hit: str
    reason: str
    timestamp: str
    approved: Optional[bool] = None     # set after approval response


# ---------------------------------------------------------------------------
# Health / bootstrap / world
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    service: str = "agent-hypervisor-browser-demo"


class BootstrapResponse(BaseModel):
    host: str
    port: int
    base_url: str
    session_token: str
    version: str


class WorldConfig(BaseModel):
    trust_defaults: dict[str, str]
    taint_defaults: dict[str, str]
    intent_policy_summary: list[dict[str, str]]
    version: str = "1.0"
