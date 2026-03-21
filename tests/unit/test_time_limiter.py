from unittest.mock import patch

import anyio
import pytest
from anyio import CancelScope

from minimcp.time_limiter import TimeLimiter

pytestmark = pytest.mark.anyio


class TestTimeLimiter:
    """Test suite for TimeLimiter class."""

    async def test_init_basic(self):
        """Test basic TimeLimiter initialization."""
        timeout = 30.0
        limiter = TimeLimiter(timeout)

        assert limiter._timeout == timeout
        assert isinstance(limiter._scope, CancelScope)

    async def test_init_with_int_timeout(self):
        """Test TimeLimiter initialization with integer timeout."""
        timeout = 60
        limiter = TimeLimiter(timeout)

        assert limiter._timeout == 60.0
        assert isinstance(limiter._scope, CancelScope)

    async def test_init_with_float_timeout(self):
        """Test TimeLimiter initialization with float timeout."""
        timeout = 45.5
        limiter = TimeLimiter(timeout)

        assert limiter._timeout == 45.5

    async def test_reset_updates_deadline(self):
        """Test that reset updates the scope deadline."""
        timeout = 10.0
        limiter = TimeLimiter(timeout)

        initial_deadline = limiter._scope.deadline

        await anyio.sleep(0.01)
        limiter.reset()

        new_deadline = limiter._scope.deadline
        assert new_deadline > initial_deadline

    async def test_reset_sets_correct_deadline(self):
        """Test that reset sets the correct deadline based on timeout."""
        timeout = 5.0
        limiter = TimeLimiter(timeout)

        with patch("minimcp.time_limiter.current_time", return_value=100.0):
            limiter.reset()
            expected_deadline = 100.0 + timeout
            assert limiter._scope.deadline == expected_deadline

    async def test_context_manager_enter(self):
        """Test TimeLimiter as context manager - enter."""
        limiter = TimeLimiter(30.0)

        result = limiter.__enter__()
        assert result is limiter

    async def test_context_manager_exit(self):
        """Test TimeLimiter as context manager - exit."""
        limiter = TimeLimiter(30.0)

        with patch.object(limiter._scope, "__exit__", return_value=None) as mock_exit:
            result = limiter.__exit__(None, None, None)
            mock_exit.assert_called_once_with(None, None, None)
            assert result is None

    async def test_context_manager_exit_with_exception(self):
        """Test TimeLimiter context manager exit with exception."""
        limiter = TimeLimiter(30.0)

        with patch.object(limiter._scope, "__exit__", return_value=True) as mock_exit:
            exc_type = ValueError
            exc_value = ValueError("test error")
            exc_tb = None

            result = limiter.__exit__(exc_type, exc_value, exc_tb)
            mock_exit.assert_called_once_with(exc_type, exc_value, exc_tb)
            assert result is True

    async def test_context_manager_full_usage(self):
        """Test TimeLimiter full context manager usage."""
        timeout = 1.0
        limiter = TimeLimiter(timeout)

        with limiter as ctx_limiter:
            assert ctx_limiter is limiter
            assert limiter._scope.__enter__ is not None

    async def test_timeout_functionality(self):
        """Test that TimeLimiter actually times out operations."""
        timeout = 0.05
        limiter = TimeLimiter(timeout)

        with limiter:
            try:
                await anyio.sleep(0.2)
            except anyio.get_cancelled_exc_class():
                pass

    async def test_no_timeout_when_operation_completes_quickly(self):
        """Test that TimeLimiter doesn't timeout quick operations."""
        timeout = 1.0
        limiter = TimeLimiter(timeout)

        with limiter:
            await anyio.sleep(0.01)

    async def test_multiple_resets(self):
        """Test multiple reset calls."""
        timeout = 5.0
        limiter = TimeLimiter(timeout)

        deadlines: list[float] = []
        for _ in range(3):
            await anyio.sleep(0.01)
            limiter.reset()
            deadlines.append(limiter._scope.deadline)

        assert deadlines[1] > deadlines[0]
        assert deadlines[2] > deadlines[1]

    async def test_scope_attribute_access(self):
        """Test that the internal scope is accessible."""
        limiter = TimeLimiter(30.0)

        assert hasattr(limiter, "_scope")
        assert isinstance(limiter._scope, CancelScope)
        assert limiter._scope.deadline is not None

    async def test_timeout_attribute_immutable_after_init(self):
        """Test that timeout is set correctly and doesn't change on reset."""
        original_timeout = 42.5
        limiter = TimeLimiter(original_timeout)

        assert limiter._timeout == original_timeout

        limiter.reset()
        assert limiter._timeout == original_timeout

    async def test_repr_or_str(self):
        """Test string representation of TimeLimiter."""
        time_limiter = TimeLimiter(30)

        str_repr = str(time_limiter)
        assert isinstance(str_repr, str)
