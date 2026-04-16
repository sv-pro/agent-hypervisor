"""
Minimal session-token authentication for local demo.

The extension sends the token in the X-Session-Token header.
The /health and /bootstrap endpoints are intentionally public so the
extension can discover the service before it has the token.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status


async def require_token(x_session_token: str = Header(default="")):
    from .main import get_config

    cfg = get_config()
    if x_session_token != cfg.session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Session-Token header",
        )
