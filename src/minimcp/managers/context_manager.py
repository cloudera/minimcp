import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Generic, TypeVar

from mcp.types import JSONRPCMessage

from minimcp.exceptions import ContextError
from minimcp.limiter import TimeLimiter
from minimcp.responder import Responder

logger = logging.getLogger(__name__)


ScopeT = TypeVar("ScopeT", bound=object)


@dataclass(slots=True)  # Use NamedTuple once MCP drops support for Python 3.10
class Context(Generic[ScopeT]):
    """
    Context object holds request metadata available to message handlers.

    The Context provides access to the current message, time limiter for managing
    idle timeout, optional scope object for passing custom data (auth, user info,
    session data, database handles, etc.), and optional responder for sending
    notifications back to the client.

    Attributes:
        message: The parsed JSON-RPC request message being handled.
        time_limiter: TimeLimiter for managing handler idle timeout. Call
            time_limiter.reset() to extend the deadline during active processing.
        scope: Optional scope object passed to mcp.handle(). Use this to pass
            authentication details, user info, session data, or database handles
            to your handlers.
        responder: Optional responder for sending notifications to the client.
            Available when bidirectional communication is supported by the transport.
    """

    message: JSONRPCMessage
    time_limiter: TimeLimiter
    scope: ScopeT | None = None
    responder: Responder | None = None


class ContextManager(Generic[ScopeT]):
    """
    ContextManager tracks the currently active handler context.

    The ContextManager provides access to request metadata (such as the message,
    scope, responder, and timeout) directly inside handlers. It uses contextvars
    to maintain thread-safe and async-safe context isolation across concurrent
    handler executions.

    You can retrieve the current context using mcp.context.get(). If called
    outside of a handler, this method raises a ContextError.

    For common use cases, helper methods (get_scope, get_responder) are provided
    to avoid null checks when accessing optional context attributes.
    """

    _ctx: ContextVar[Context[ScopeT]] = ContextVar("ctx")

    @contextmanager
    def active(self, context: Context[ScopeT]):
        """Set the active context for the current handler execution.

        This context manager sets the context at the start of handler execution
        and clears it when the handler completes, ensuring proper cleanup.

        Args:
            context: The context to make active during handler execution.

        Yields:
            None. The context is accessible via get() during execution.
        """
        # Set context
        token: Token[Context[ScopeT]] = self._ctx.set(context)
        try:
            yield
        finally:
            # Clear context
            self._ctx.reset(token)

    def get(self) -> Context[ScopeT]:
        """Get the current handler context.

        Returns:
            The active Context object containing message, time_limiter, scope,
            and responder.

        Raises:
            ContextError: If called outside of an active handler context.
        """
        try:
            return self._ctx.get()
        except LookupError as e:
            msg = "No Context: Called mcp.context.get() outside of an active handler context"
            logger.error(msg)
            raise ContextError(msg) from e

    def get_scope(self) -> ScopeT:
        """Get the scope object from the current context.

        This helper method retrieves the scope and raises an error if it's not
        available, avoiding the need for null checks in your code.

        Returns:
            The scope object passed to mcp.handle().

        Raises:
            ContextError: If called outside of an active handler context or if
                no scope was provided to mcp.handle().
        """
        scope = self.get().scope
        if scope is None:
            raise ContextError("ContextError: Scope is not available in current context")
        return scope

    def get_responder(self) -> Responder:
        """Get the responder from the current context.

        This helper method retrieves the responder and raises an error if it's not
        available, avoiding the need for null checks in your code. The responder
        is only available when using transports that support bidirectional
        communication (stdio, Streamable HTTP).

        Returns:
            The Responder for sending notifications to the client.

        Raises:
            ContextError: If called outside of an active handler context or if
                the responder is not available (e.g., when using HTTP transport).
        """
        responder = self.get().responder
        if responder is None:
            raise ContextError("ContextError: Responder is not available in current context")
        return responder
