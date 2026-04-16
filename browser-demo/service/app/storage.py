"""
In-memory event store keyed by event_id.

Keeps the last MAX_EVENTS events; older ones are evicted.
No database required for this local demo.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

from .models import PageEvent

MAX_EVENTS = 500


class EventStore:
    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._lock = threading.Lock()
        self._store: OrderedDict[str, dict] = OrderedDict()
        self._max = max_events

    def put(self, event_id: str, event: PageEvent, trust: str, taint: bool) -> None:
        with self._lock:
            self._store[event_id] = {
                "event": event,
                "trust": trust,
                "taint": taint,
            }
            if len(self._store) > self._max:
                self._store.popitem(last=False)

    def get(self, event_id: str) -> Optional[dict]:
        with self._lock:
            return self._store.get(event_id)

    def size(self) -> int:
        with self._lock:
            return len(self._store)
