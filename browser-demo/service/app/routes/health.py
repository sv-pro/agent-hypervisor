from fastapi import APIRouter
from ..models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
async def health(config=None):
    from ..main import get_config
    cfg = get_config()
    return HealthResponse(version=cfg.version)
