import logging
from typing import Any

from anyio import CancelScope, current_time

logger = logging.getLogger(__name__)


class TimeLimiter:
    """Enforces an idle timeout for a single message handler.

    The timer can be reset during handler execution to extend the deadline,
    preventing timeout when the handler is actively processing.

    Used as a synchronous context manager — the cancel scope is entered on
    ``__enter__`` and exited on ``__exit__``.
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
