"""
sse_transport.py — SSE transport layer for the MCP gateway.

Implements the MCP 2024-11-05 SSE transport:

  1. Client GETs /mcp/sse  →  server opens an SSE stream and sends an
     'endpoint' event containing the POST URL the client should use.
  2. Client POSTs JSON-RPC requests to /mcp/messages?session_id=<id>.
  3. Server processes the request and sends the JSON-RPC response back
     over the SSE stream as a 'message' event.

This makes the gateway compatible with MCP clients that require streaming
(e.g., Claude Desktop). The existing HTTP POST /mcp endpoint is unaffected.

Classes:
    SSESessionStore — registry of active SSE sessions (session_id → Queue)

Functions:
    format_sse_event(event, data) → str
    sse_stream(session_id, queue, endpoint_url, store) → AsyncGenerator
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator, Optional

# Timeout (seconds) between heartbeat pings sent to the client to keep the
# connection alive through proxies and load-balancers.
_HEARTBEAT_INTERVAL: float = 25.0


class SSESessionStore:
    """
    Registry of active SSE sessions.

    Each GET /mcp/sse connection creates a session: a UUID is assigned and an
    asyncio Queue is stored here. When the client POSTs to /mcp/messages, the
    response is placed in the queue. The SSE stream reads from the queue and
    forwards the response as a 'message' event.

    Sessions are removed automatically when the SSE stream generator exits
    (client disconnect or server shutdown).

    Thread safety: Python dict operations are GIL-atomic; this is safe for
    asyncio single-threaded event loop usage. Do not share across threads.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, asyncio.Queue] = {}

    def create_session(self) -> tuple[str, asyncio.Queue]:
        """
        Create a new SSE session.

        Returns:
            (session_id, queue) — caller keeps the queue reference for
            the streaming generator; session_id is sent to the client
            as part of the endpoint URL.
        """
        session_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        self._sessions[session_id] = queue
        return session_id, queue

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        """
        Look up the queue for an existing session.

        Returns None if the session does not exist (client already disconnected
        or invalid session_id).
        """
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        """Remove a session from the registry (idempotent)."""
        self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        """Return the number of currently active SSE sessions."""
        return len(self._sessions)

    def active_session_ids(self) -> list[str]:
        """Return a snapshot list of active session IDs."""
        return list(self._sessions.keys())


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------

def format_sse_event(event: str, data: str) -> str:
    """
    Format a single SSE event.

    SSE wire format:
        event: <event-name>\\n
        data: <payload>\\n
        \\n

    Args:
        event: Event name (e.g. 'endpoint', 'message').
        data:  Event payload string. Multi-line data is not supported here
               (MCP responses are single JSON objects on one line).

    Returns:
        SSE-encoded string ready to be yielded from a StreamingResponse.
    """
    return f"event: {event}\ndata: {data}\n\n"


# ---------------------------------------------------------------------------
# SSE stream generator
# ---------------------------------------------------------------------------

async def sse_stream(
    session_id: str,
    queue: asyncio.Queue,
    endpoint_url: str,
    store: SSESessionStore,
) -> AsyncGenerator[str, None]:
    """
    Async generator for an MCP SSE transport stream.

    Protocol:
        1. Yields an 'endpoint' event immediately. The data is the URL where
           the client should POST JSON-RPC requests, e.g.:
               /mcp/messages?session_id=<uuid>
        2. Yields 'message' events for each JSON-RPC response placed in the
           queue by POST /mcp/messages.
        3. Sends a comment-only keep-alive ping every _HEARTBEAT_INTERVAL
           seconds to prevent proxy timeouts.
        4. Stops when a None sentinel is placed in the queue (graceful
           shutdown) or when the client disconnects (GeneratorExit).

    Cleanup:
        Removes the session from the store in a finally block so that
        subsequent POST /mcp/messages for the same session_id return 404.

    Args:
        session_id:   The session UUID assigned to this connection.
        queue:        The asyncio Queue for this session. Responses from
                      POST /mcp/messages are placed here.
        endpoint_url: The URL to send in the initial 'endpoint' event.
        store:        The SSESessionStore; used for cleanup on disconnect.
    """
    try:
        # Step 1: send the endpoint event so the client knows where to POST
        yield format_sse_event("endpoint", endpoint_url)

        # Step 2 & 3: stream responses, heartbeat on timeout
        while True:
            try:
                payload = await asyncio.wait_for(
                    queue.get(), timeout=_HEARTBEAT_INTERVAL
                )
            except asyncio.TimeoutError:
                # Keep-alive ping (SSE comment — clients ignore it)
                yield ": ping\n\n"
                continue

            if payload is None:
                # Graceful shutdown sentinel
                break

            yield format_sse_event("message", payload)

    finally:
        store.remove_session(session_id)
