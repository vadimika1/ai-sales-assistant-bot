from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> int | None:
        now = time.monotonic()
        window_start = now - self.window_seconds

        with self._lock:
            queue = self._events[key]
            while queue and queue[0] < window_start:
                queue.popleft()

            if len(queue) >= self.limit:
                retry_after = int(max(1.0, self.window_seconds - (now - queue[0])))
                return retry_after

            queue.append(now)
            return None
