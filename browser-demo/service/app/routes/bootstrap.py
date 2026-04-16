"""
/bootstrap — public endpoint (no auth required).

Returns enough information for any client to connect to the service.
The session token is returned here so the extension can use it for
subsequent authenticated calls.
"""
from fastapi import APIRouter
from ..models import BootstrapResponse

router = APIRouter()


@router.get("/bootstrap", response_model=BootstrapResponse, tags=["meta"])
async def bootstrap():
    from ..main import get_config
    cfg = get_config()
    return BootstrapResponse(
        host=cfg.host,
        port=cfg.port,
        base_url=cfg.base_url,
        session_token=cfg.session_token,
        version=cfg.version,
    )
