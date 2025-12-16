import logging
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from http import HTTPStatus
from types import TracebackType
from typing import Any, NamedTuple

import anyio
from anyio.abc import TaskGroup, TaskStatus
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from typing_extensions import override

from minimcp.exceptions import MCPRuntimeError, MiniMCPError
from minimcp.managers.context_manager import ScopeT
from minimcp.minimcp import MiniMCP
from minimcp.transports.base_http import MEDIA_TYPE_JSON, BaseHTTPTransport, MCPHTTPResponse
from minimcp.types import MESSAGE_ENCODING, Message

logger = logging.getLogger(__name__)


MEDIA_TYPE_SSE = "text/event-stream"

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "Content-Type": MEDIA_TYPE_SSE,
}


class MCPStreamingHTTPResponse(NamedTuple):
    """
    Represents the response from a MiniMCP server to a client HTTP request.

    Attributes:
        status_code: The HTTP status code to return to the client.
        content: The response content as a MemoryObjectReceiveStream.
        media_type: The MIME type of the response response stream ("text/event-stream").
        headers: Additional HTTP headers to include in the response.
    """

    status_code: HTTPStatus
    content: MemoryObjectReceiveStream[str]
    headers: Mapping[str, str] = SSE_HEADERS
    media_type: str = MEDIA_TYPE_SSE


class StreamManager:
    """
    Manages the lifecycle of memory object streams for the StreamableHTTPTransport.

    Streams are created on demand - Once streaming is activated, the receive stream
    is handed off to the consumer via on_create callback, while the send stream
    remains owned by the StreamManager.

    Once the handling completes, the close method needs to be called manually to close
    the streams gracefully - Not using a context manager to keep the approach explicit.

    On close, the send stream is closed immediately and the receive stream is closed after
    a configurable delay to allow consumers to finish draining the stream. The cleanup is
    shielded from cancellation to prevent resource leaks when tasks are cancelled during
    transport shutdown.
    """

    _lock: anyio.Lock
    _on_create: Callable[[MCPStreamingHTTPResponse], None]

    _send_stream: MemoryObjectSendStream[Message] | None
    _receive_stream: MemoryObjectReceiveStream[Message] | None

    def __init__(self, on_create: Callable[[MCPStreamingHTTPResponse], None]) -> None:
        """
        Args:
            on_create: Callback to be called when the streams are created.
        """
        self._on_create = on_create
        self._lock = anyio.Lock()

        self._send_stream = None
        self._receive_stream = None

    def is_streaming(self) -> bool:
        """
        Returns:
            True if the streams are created and ready to be used, False otherwise.
        """
        return self._send_stream is not None and self._receive_stream is not None

    async def create_and_send(self, message: Message, create_timeout: float = 0.1) -> None:
        """
        Creates the streams and sends the message. If the streams are already available,
        it sends the message over the existing streams.

        Args:
            message: Message to send.
            create_timeout: Timeout to create the streams.
        """
        if self._send_stream is None:
            with anyio.fail_after(create_timeout):
                async with self._lock:
                    if self._send_stream is None:
                        send_stream, receive_stream = anyio.create_memory_object_stream[Message](0)
                        self._on_create(MCPStreamingHTTPResponse(HTTPStatus.OK, receive_stream))
                        self._send_stream = send_stream
                        self._receive_stream = receive_stream

        await self.send(message)

    async def send(self, message: Message) -> None:
        """
        Sends the message to the send stream.

        Args:
            message: Message to send.

        Raises:
            MiniMCPError: If the send stream is unavailable.
        """
        if self._send_stream is None:
            raise MiniMCPError("Send stream is unavailable")

        try:
            await self._send_stream.send(message)
        except (anyio.BrokenResourceError, anyio.ClosedResourceError) as e:
            # Consumer went away or stream closed or stream not created; ignore further sends.
            logger.debug("Failed to send message: consumer disconnected. Error: %s", e)
            pass

    async def close(self, receive_close_delay: float) -> None:
        """
        Closes the send and receive streams gracefully if they were created by the StreamManager.
        After closing the send stream, it waits for the receive stream to be closed by the consumer. If the
        consumer does not close the receive stream, it will be closed after the delay.

        Args:
            receive_close_delay: Delay to wait for the receive stream to be closed by the consumer.
        """
        if self._send_stream is not None:
            try:
                await self._send_stream.aclose()
            except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                pass

        if self._receive_stream is not None:
            try:
                with anyio.CancelScope(shield=True):
                    await anyio.sleep(receive_close_delay)
                    await self._receive_stream.aclose()
            except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                pass


# TODO: Add resumability based on Last-Event-ID header on GET method.
class StreamableHTTPTransport(BaseHTTPTransport[ScopeT]):
    """
    Adds support for MCP's streamable HTTP transport mechanism.
    More details @ https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http

    With Streamable HTTP the MCP server can operates as an independent process that can handle multiple
    client connections using HTTP.

    Security Warning: Security is not provided inbuilt. It is the responsibility of the web framework to
    provide security.
    """

    _ping_interval: int
    _receive_close_delay: float

    _tg: TaskGroup | None

    RESPONSE_MEDIA_TYPES: frozenset[str] = frozenset[str]([MEDIA_TYPE_JSON, MEDIA_TYPE_SSE])
    SUPPORTED_HTTP_METHODS: frozenset[str] = frozenset[str](["POST"])

    def __init__(
        self,
        minimcp: MiniMCP[ScopeT],
        ping_interval: int = 15,
        receive_close_delay: float = 0.1,
    ) -> None:
        """
        Args:
            minimcp: The MiniMCP instance to use.
            ping_interval: The ping interval in seconds to keep the streams alive. By default, it is set to
                15 seconds based on a widely adopted convention.
            receive_close_delay: After request handling is complete, wait for these many seconds before
                automatically closing the receive stream. By default, it is set to 0.1 seconds to allow
                the consumer to finish draining the stream.
        """
        super().__init__(minimcp)
        self._ping_interval = ping_interval
        self._receive_close_delay = receive_close_delay
        self._tg = None

    async def __aenter__(self) -> "StreamableHTTPTransport[ScopeT]":
        self._tg = await anyio.create_task_group().__aenter__()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> bool | None:
        if self._tg is not None:
            logger.debug("Shutting down StreamableHTTPTransport")

            # Cancel all background tasks to prevent hanging on.
            self._tg.cancel_scope.cancel()

            # Exit the task group
            result = await self._tg.__aexit__(exc_type, exc, tb)

            if self._tg.cancel_scope.cancelled_caught:
                logger.warning("Background tasks were cancelled during StreamableHTTPTransport shutdown")

            self._tg = None
            return result
        return None

    @asynccontextmanager
    async def lifespan(self, _: Any) -> AsyncGenerator[None, None]:
        """
        Provides an easy to use lifespan context manager for the StreamableHTTPTransport.
        """
        async with self:
            yield

    @override
    async def dispatch(
        self, method: str, headers: Mapping[str, str], body: str, scope: ScopeT | None = None
    ) -> MCPHTTPResponse | MCPStreamingHTTPResponse:
        """
        Dispatch an HTTP request to the MiniMCP server.

        Args:
            method: The HTTP method of the request.
            headers: HTTP request headers.
            body: HTTP request body as a string.
            scope: Optional message scope passed to the MiniMCP server.

        Returns:
            MCPHTTPResponse object with the response from the MiniMCP server.
        """

        if self._tg is None:
            raise MCPRuntimeError(
                "dispatch can only be used inside an 'async with' block or a lifespan of StreamableHTTPTransport"
            )

        logger.debug("Handling HTTP request. Method: %s, Headers: %s", method, headers)

        if method == "POST":
            # Start _handle_post_request in a separate task and await for readiness.
            # Once ready _handle_post_request_task returns a MCPHTTPResponse or MCPStreamingHTTPResponse.
            return await self._tg.start(self._handle_post_request_task, headers, body, scope)
        else:
            return self._handle_unsupported_request()

    @override
    async def starlette_dispatch(self, request: Request, scope: ScopeT | None = None) -> Response:
        """
        Dispatch a Starlette request to the MiniMCP server and return the response as a Starlette response object.

        Args:
            request: Starlette request object.
            scope: Optional message scope passed to the MiniMCP server.

        Returns:
            MiniMCP server response formatted as a Starlette Response object.
        """
        msg = await request.body()
        body_str = msg.decode(MESSAGE_ENCODING)
        result = await self.dispatch(request.method, request.headers, body_str, scope)

        if isinstance(result, MCPStreamingHTTPResponse):
            return EventSourceResponse(result.content, headers=result.headers, ping=self._ping_interval)

        return Response(result.content, result.status_code, result.headers, result.media_type)

    @override
    def as_starlette(self, path: str = "/", debug: bool = False) -> Starlette:
        """
        Provide the HTTP transport as a Starlette application.

        Args:
            path: The path to the MCP application endpoint.
            debug: Whether to enable debug mode.

        Returns:
            Starlette application.
        """

        route = Route(path, endpoint=self.starlette_dispatch, methods=self.SUPPORTED_HTTP_METHODS)

        logger.info("Creating MCP application at path: %s", path)
        return Starlette(routes=[route], debug=debug, lifespan=self.lifespan)

    async def _handle_post_request_task(
        self,
        headers: Mapping[str, str],
        body: str,
        scope: ScopeT | None,
        task_status: TaskStatus[MCPHTTPResponse | MCPStreamingHTTPResponse],
    ):
        """
        This is the special sauce that makes the smart StreamableHTTPTransport possible.
        _handle_post_request_task runs as a separate task and manages the handler execution. Once ready, it sends a
        MCPHTTPResponse via the task_status. If the handler calls the send callback, streaming is activated,
        else it acts like a regular HTTP transport. For streaming, _handle_post_request_task sends a MCPHTTPResponse
        with a MemoryObjectReceiveStream as the content and continues running in the background until
        the handler finishes executing.

        Args:
            headers: HTTP request headers.
            body: HTTP request body as a string.
            scope: Optional message scope passed to the MiniMCP server.
            task_status: Task status object to communicate task readiness and result.
        """

        stream_manager = StreamManager(on_create=task_status.started)
        not_completed = True

        try:
            result = await self._handle_post_request(headers, body, scope, send_callback=stream_manager.create_and_send)

            if stream_manager.is_streaming():
                if result.content:
                    await stream_manager.send(result.content)
            else:
                task_status.started(result)

            not_completed = False
        finally:
            if stream_manager.is_streaming():
                await stream_manager.close(self._receive_close_delay)
            elif not_completed:
                # This should never happen, _handle_post_request should handle all exceptions,
                # but adding this fallback to ensure the task is always started.
                try:
                    error = MCPRuntimeError("Task was not completed by StreamableHTTPTransport")
                    task_status.started(self._build_error_response(error, body))
                except RuntimeError as e:
                    logger.error("Task is not completed: %s", e)
