"""
GET /world/current — return the active world policy config.
"""
from fastapi import APIRouter, Depends

from ..auth import require_token

router = APIRouter()


@router.get(
    "/world/current",
    dependencies=[Depends(require_token)],
    tags=["world"],
)
async def world_current():
    from ..main import get_config
    from ..world import current_world

    cfg = get_config()
    return current_world(cfg.version).model_dump()
