import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from anyio import CancelScope, CapacityLimiter, current_time

logger = logging.getLogger(__name__)


class TimeLimiter:
    """
    TimeLimiter enforces an idle timeout for message handlers.

    The timer can be reset during handler execution to extend the deadline,
    preventing timeout when the handler is actively processing.
    """

    _timeout: float
    _scope: CancelScope

    def __init__(self, timeout: float):
        """
        Args:
            timeout: The idle timeout in seconds.
        """
        self._timeout = float(timeout)
        self._scope = CancelScope()
        self.reset()

    def reset(self) -> None:
        """Reset the idle timeout, extending the deadline from the current time."""
        self._scope.deadline = current_time() + self._timeout

    def __enter__(self):
        self._scope.__enter__()
        return self

    def __exit__(self, *args: Any):
        return self._scope.__exit__(*args)


class Limiter:
    """
    Limiter enforces concurrency and idle timeout limits for MiniMCP message handlers.

    MiniMCP controls how many handlers can run at the same time (max_concurrency)
    and how long each handler can remain idle (idle_timeout) before being cancelled.
    By default, idle_timeout is set to 30 seconds and max_concurrency to 100 in MiniMCP.

    The TimeLimiter returned by this limiter is available in the handler context
    and can be reset using time_limiter.reset() to extend the deadline during
    active processing.

    Yields:
        A TimeLimiter that can be used to reset the idle timeout during handler execution.
    """

    _idle_timeout: int

    def __init__(self, idle_timeout: int, max_concurrency: int) -> None:
        """
        Args:
            idle_timeout: The idle timeout in seconds. Handlers exceeding this timeout
                will be cancelled if they don't reset the timer.
            max_concurrency: The maximum number of concurrent message handlers allowed.
                Additional requests will wait until a slot becomes available.
        """
        self._idle_timeout = idle_timeout
        self._capacity_limiter = CapacityLimiter(max_concurrency)

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[TimeLimiter, None]:
        async with self._capacity_limiter:
            with TimeLimiter(self._idle_timeout) as time_limiter:
                yield time_limiter
