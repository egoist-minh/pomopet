import math
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        super().__init__("Local chat rate limit exceeded")
        self.retry_after_seconds = max(1, retry_after_seconds)


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


class SlidingWindowRateLimiter:
    """Small in-process limiter for the local, single-instance backend."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("Rate-limit values must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, key: str) -> None:
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.max_requests:
                retry_after = math.ceil(timestamps[0] + self.window_seconds - now)
                raise RateLimitExceeded(retry_after)
            timestamps.append(now)

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


chat_rate_limiter = SlidingWindowRateLimiter(
    max_requests=_positive_int_from_env("CHAT_RATE_LIMIT_REQUESTS", 5),
    window_seconds=_positive_int_from_env("CHAT_RATE_LIMIT_WINDOW_SECONDS", 60),
)
