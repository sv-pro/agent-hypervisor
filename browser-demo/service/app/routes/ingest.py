"""
POST /ingest_page — receive a page event and return trust/taint/actions.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from ..auth import require_token
from ..models import IngestResponse, PageEvent
from ..policy import assign_taint, assign_trust, available_actions

router = APIRouter()


def _make_event_id(url: str, ts: str) -> str:
    raw = f"{url}:{ts}"
    return "evt-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


@router.post(
    "/ingest_page",
    response_model=IngestResponse,
    dependencies=[Depends(require_token)],
    tags=["core"],
)
async def ingest_page(event: PageEvent):
    from ..main import get_event_store

    if not event.captured_at:
        event = event.model_copy(
            update={"captured_at": datetime.now(timezone.utc).isoformat()}
        )
    if not event.content_hash:
        event = event.model_copy(
            update={
                "content_hash": "sha256:"
                + hashlib.sha256(event.visible_text.encode()).hexdigest()
            }
        )

    trust = assign_trust(event.source_type)
    taint = assign_taint(trust, event.hidden_content_detected)
    event_id = _make_event_id(event.url, event.captured_at)

    get_event_store().put(event_id, event, trust, taint)

    actions = available_actions(trust, taint)
    return IngestResponse(
        event_id=event_id,
        trust=trust,
        taint=taint,
        available_actions=actions,
        message="Page ingested successfully",
    )
