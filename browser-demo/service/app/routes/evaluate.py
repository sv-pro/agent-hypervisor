"""
POST /evaluate — evaluate an intent against the deterministic policy.
POST /approval/respond — respond to an "ask" decision.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_token
from ..models import ApprovalRequest, ApprovalResponse, EvaluateRequest, EvaluateResponse
from ..policy import evaluate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    dependencies=[Depends(require_token)],
    tags=["core"],
)
async def evaluate_intent(req: EvaluateRequest):
    from ..main import get_event_store, get_trace_store
    from ..models import TraceEntry

    record = get_event_store().get(req.event_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Event '{req.event_id}' not found. Call /ingest_page first.",
        )

    event = record["event"]
    trust: str = record["trust"]
    taint: bool = record["taint"]

    decision = evaluate(
        intent_type=req.intent_type,
        trust=trust,
        taint=taint,
        hidden_content_detected=event.hidden_content_detected,
    )

    trace_id = "tr-" + uuid.uuid4().hex[:12]
    entry = TraceEntry(
        trace_id=trace_id,
        event_id=req.event_id,
        intent_type=req.intent_type,
        trust=trust,
        taint=taint,
        decision=decision.decision,
        rule_hit=decision.rule_hit,
        reason=decision.reason,
        timestamp=_now(),
    )
    get_trace_store().append(entry)

    return EvaluateResponse(
        decision=decision.decision,
        rule_hit=decision.rule_hit,
        reason=decision.reason,
        trace_id=trace_id,
    )


@router.post(
    "/approval/respond",
    response_model=ApprovalResponse,
    dependencies=[Depends(require_token)],
    tags=["core"],
)
async def approval_respond(req: ApprovalRequest):
    from ..main import get_trace_store

    updated = get_trace_store().update_approval(req.trace_id, req.approved)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Trace '{req.trace_id}' not found in recent history.",
        )

    final = "allow" if req.approved else "deny"
    return ApprovalResponse(
        trace_id=req.trace_id,
        final_decision=final,
        message=f"User {'approved' if req.approved else 'denied'} the pending action.",
    )
