"""A tiny in-process sliding-window limiter for the public demo.

All visitors of a demo share one LLM API quota, so the limit is global (per process), not per IP.
"""

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_s: float = 3600) -> None:
        self.max_calls, self.window_s = max_calls, window_s
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_next_slot)."""
        now = time.monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] > self.window_s:
                self._calls.popleft()
            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return True, 0
            if not self._calls:  # a limit of 0 means "always refuse"
                return False, int(self.window_s)
            return False, int(self.window_s - (now - self._calls[0])) + 1
