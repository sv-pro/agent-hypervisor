"""
GET /trace/recent — return recent trace entries.
"""
from fastapi import APIRouter, Depends, Query

from ..auth import require_token

router = APIRouter()


@router.get(
    "/trace/recent",
    dependencies=[Depends(require_token)],
    tags=["trace"],
)
async def recent_trace(limit: int = Query(default=20, ge=1, le=200)):
    from ..main import get_trace_store

    entries = get_trace_store().recent(limit=limit)
    return {"entries": [e.model_dump() for e in reversed(entries)], "count": len(entries)}
