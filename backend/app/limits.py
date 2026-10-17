"""Per-visitor limits on the two actions that cost money or disturb everyone: "Draft with AI" (a Gemini call on every
click) and "Reset demo data" (reloads the shared demo and makes the AI analyse every card again). The numbers are in
config/settings.toml ([limits]). Counts live in memory: the backend runs one instance, and a limit only needs to hold for
a few minutes. A shared cache (Memorystore) would hold them across several instances (future scope)."""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Optional


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._uses: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> Optional[int]:
        """Counts one use. None = allowed; otherwise the whole minutes until the next use is allowed (at least 1).
        A refused try is not counted, so waiting is always enough."""
        if limit <= 0:
            return None   # 0 in the settings = no limit
        now = self._clock()
        with self._lock:
            uses = self._uses[key]
            while uses and uses[0] <= now - window_seconds:
                uses.popleft()
            if len(uses) >= limit:
                return max(1, math.ceil((uses[0] + window_seconds - now) / 60))
            uses.append(now)
            return None


def visitor_key(person_id: Optional[str], forwarded_for: Optional[str], client_host: Optional[str]) -> str:
    """Who is asking: the signed-in person, or a guest's address (Cloud Run puts the visitor's address first in
    X-Forwarded-For). Switching demo persons does not reset a guest's count."""
    if person_id:
        return f"person:{person_id}"
    address = (forwarded_for or "").split(",")[0].strip() or client_host or "unknown"
    return f"guest:{address}"
