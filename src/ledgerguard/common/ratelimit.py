from __future__ import annotations

import threading
from collections import deque

from ledgerguard.common.clock import Clock
from ledgerguard.common.errors import rate_limited


class RateLimiter:
    def __init__(self, clock: Clock, window_seconds: int) -> None:
        self._clock = clock
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    # ————————————————————————————————————————

    def check(self, key: str, limit: int) -> None:
        now = self._clock.now().timestamp()
        with self._lock:
            queue = self._hits.setdefault(key, deque())
            while queue and now - queue[0] >= self._window:
                queue.popleft()
            if len(queue) >= limit:
                raise rate_limited()
            queue.append(now)

    # ————————————————————————————————————————

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
