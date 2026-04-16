"""
Agent Hypervisor Browser Demo — FastAPI service entry point.

Run with:
    cd browser-demo/service
    uvicorn app.main:app --host 127.0.0.1 --port 17841

Or use the helper script:
    python -m app.main
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import remove_bootstrap, write_bootstrap
from .config import ServiceConfig, load_config
from .storage import EventStore
from .trace import TraceStore

# ---------------------------------------------------------------------------
# Singletons (initialised in lifespan, accessed via getters below)
# ---------------------------------------------------------------------------

_config: ServiceConfig | None = None
_event_store: EventStore | None = None
_trace_store: TraceStore | None = None


def get_config() -> ServiceConfig:
    if _config is None:
        raise RuntimeError("Service not initialised")
    return _config


def get_event_store() -> EventStore:
    if _event_store is None:
        raise RuntimeError("Service not initialised")
    return _event_store


def get_trace_store() -> TraceStore:
    if _trace_store is None:
        raise RuntimeError("Service not initialised")
    return _trace_store


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _event_store, _trace_store

    _config = load_config()
    _event_store = EventStore()
    _trace_store = TraceStore(_config.trace_store_path)

    if _config.bootstrap_enabled:
        bpath = write_bootstrap(_config)
        print(f"[hypervisor] bootstrap written → {bpath}", flush=True)

    print(
        f"[hypervisor] service ready — {_config.base_url}  "
        f"(token: {_config.session_token})",
        flush=True,
    )

    yield   # ← service is running

    if _config.bootstrap_enabled:
        remove_bootstrap(_config)
        print("[hypervisor] bootstrap removed", flush=True)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Agent Hypervisor Browser Demo",
    version="0.1.0",
    description=(
        "Local deterministic governance kernel for the browser agent demo. "
        "The extension is a thin client; all policy decisions happen here."
    ),
    lifespan=lifespan,
)

# Allow the Chrome extension origin.
# In development the extension is loaded unpacked so it uses a
# chrome-extension:// origin that we can't know in advance.
# We restrict to local origins only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        # Chrome extension pages
        "chrome-extension://",
    ],
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from .routes import (  # noqa: E402
    bootstrap,
    evaluate,
    health,
    ingest,
    trace,
    world,
)

app.include_router(health.router)
app.include_router(bootstrap.router)
app.include_router(ingest.router)
app.include_router(evaluate.router)
app.include_router(trace.router)
app.include_router(world.router)


# ---------------------------------------------------------------------------
# __main__ entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level="info",
    )
