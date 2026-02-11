"""
Async token bucket rate limiter for ESI requests.

Allows burst traffic up to `burst_size` then throttles to a steady
`tokens_per_second` rate. Thread-safe via asyncio.Lock.
"""

import asyncio
import time


class TokenBucketRateLimiter:
    """Token bucket rate limiter for async code.

    Tokens refill continuously at `tokens_per_second`. A burst of up to
    `burst_size` requests can happen immediately; after that, acquire()
    will await until a token is available.
    """

    def __init__(self, burst_size: int = 10, tokens_per_second: float = 5.0):
        self._burst_size = burst_size
        self._tokens_per_second = tokens_per_second
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        async with self._lock:
            self._refill()
            while self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._tokens_per_second
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._burst_size,
            self._tokens + elapsed * self._tokens_per_second,
        )
        self._last_refill = now
