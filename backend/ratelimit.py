"""Простое ограничение частоты запросов в памяти процесса."""

import time
from collections import deque


class SlidingLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()

        for k in list(self._hits):
            hits = self._hits[k]

            while hits and now - hits[0] > self.window:
                hits.popleft()

            if not hits:
                del self._hits[k]

        hits = self._hits.setdefault(key, deque())

        if len(hits) >= self.limit:
            return False

        hits.append(now)
        return True
