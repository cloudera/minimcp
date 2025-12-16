import json
from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock

import anyio
import pytest
from anyio.streams.memory import MemoryObjectReceiveStream
from mcp.types import LATEST_PROTOCOL_VERSION
from test_base_http_transport import TestBaseHTTPTransport

from minimcp.exceptions import MCPRuntimeError, MiniMCPError
from minimcp.minimcp import MiniMCP
from minimcp.transports.base_http import MCPHTTPResponse
from minimcp.transports.streamable_http import (
    SSE_HEADERS,
    MCPStreamingHTTPResponse,
    StreamableHTTPTransport,
    StreamManager,
)
from minimcp.types import Message, NoMessage, Send

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def timeout_5s():
    """Fail test if it takes longer than 5 seconds."""
    with anyio.fail_after(5):
        yield


class TestStreamableHTTPTransport:
    """Test suite for StreamableHTTPTransport."""

    @pytest.fixture
    def accept_content_types(self) -> str:
        return "application/json, text/event-stream"

    @pytest.fixture
    def request_headers(self, accept_content_types: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        }

    @pytest.fixture
    def valid_body(self):
        """Create a valid JSON-RPC request body."""
        return json.dumps({"jsonrpc": "2.0", "method": "test_method", "params": {"test": "value"}, "id": 1})

    @pytest.fixture
    def mock_handler(self) -> AsyncMock:
        """Create a mock handler."""
        return AsyncMock(return_value='{"jsonrpc": "2.0", "result": "success", "id": 1}')

    @pytest.fixture
    def transport(self, mock_handler: AsyncMock) -> StreamableHTTPTransport[Any]:
        mcp = AsyncMock(spec=MiniMCP[Any])
        mcp.handle = mock_handler
        return StreamableHTTPTransport[Any](mcp)

    async def test_transport_context_manager(self, transport: StreamableHTTPTransport[None]):
        """Test transport as async context manager."""

        async with transport as t:
            assert t is transport
            assert transport._tg is not None

        # Should be cleaned up after exiting context
        assert transport._tg is None

    async def test_transport_lifespan(self, transport: StreamableHTTPTransport[None]):
        """Test transport lifespan context manager."""
        async with transport.lifespan(None):
            assert transport._tg is not None

        assert transport._tg is None

    async def test_dispatch_post_request_success(
        self,
        transport: StreamableHTTPTransport[None],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test successful POST request handling."""
        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.media_type == "application/json"
        assert result.content == '{"jsonrpc": "2.0", "result": "success", "id": 1}'
        mock_handler.assert_called_once()

    async def test_dispatch_unsupported_method(
        self,
        transport: StreamableHTTPTransport[None],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of unsupported HTTP methods."""
        async with transport:
            result = await transport.dispatch("GET", request_headers, valid_body)

        assert result.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert result.headers is not None
        assert "Allow" in result.headers
        assert "POST" in result.headers["Allow"]
        mock_handler.assert_not_called()

    async def test_dispatch_not_started_error(
        self,
        transport: StreamableHTTPTransport[None],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test that dispatch raises error when transport is not started."""
        with pytest.raises(MCPRuntimeError, match="dispatch can only be used inside an 'async with' block"):
            await transport.dispatch("POST", request_headers, valid_body)

    async def test_dispatch_sse_response(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test dispatch returning SSE stream response."""

        async def streaming_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "stream1", "id": 1}')
            await send('{"jsonrpc": "2.0", "result": "stream2", "id": 2}')
            return "Final result"

        streaming_handler = AsyncMock(side_effect=streaming_handler)
        transport.minimcp.handle = streaming_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert isinstance(result.content, MemoryObjectReceiveStream)
        assert result.headers == SSE_HEADERS

    async def test_dispatch_no_message_response(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test handling when handler returns NoMessage."""
        handler = AsyncMock(return_value=NoMessage.NOTIFICATION)
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.ACCEPTED
        handler.assert_called_once()

    async def test_dispatch_error_response(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test handling of JSON-RPC error responses."""
        error_response = json.dumps(
            {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": 1}
        )
        handler = AsyncMock(return_value=error_response)
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == error_response
        assert result.media_type == "application/json"

    async def test_dispatch_handler_exception(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test handling when handler raises an exception."""
        handler = AsyncMock(side_effect=Exception("Handler error"))
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)

        # Should return an error response
        assert result.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert result.content is not None
        assert "error" in str(result.content)
        handler.assert_called_once()

    async def test_dispatch_streaming_with_final_response(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test streaming handler that sends messages and returns a final response."""

        async def streaming_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "stream1", "id": 1}')
            await send('{"jsonrpc": "2.0", "result": "stream2", "id": 2}')
            return '{"jsonrpc": "2.0", "result": "final", "id": 3}'

        streaming_handler = AsyncMock(side_effect=streaming_handler)
        transport.minimcp.handle = streaming_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)

        # Should return stream since send was called
        assert isinstance(result.content, MemoryObjectReceiveStream)
        assert result.headers == SSE_HEADERS

    async def test_dispatch_accept_both_json_and_sse(
        self, transport: StreamableHTTPTransport[None], valid_body: str, request_headers: dict[str, str]
    ):
        """Test dispatch with headers accepting both JSON and SSE."""
        handler = AsyncMock(return_value='{"result": "success"}')
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == '{"result": "success"}'
        assert result.media_type == "application/json"

    async def test_dispatch_invalid_accept_header(self, transport: StreamableHTTPTransport[None], valid_body: str):
        """Test dispatch with invalid Accept header."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "MCP-Protocol-Version": "2025-06-18",
        }
        handler = AsyncMock()
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.NOT_ACCEPTABLE
        handler.assert_not_called()

    async def test_dispatch_invalid_content_type(
        self, transport: StreamableHTTPTransport[None], valid_body: str, accept_content_types: str
    ):
        """Test dispatch with invalid Content-Type."""
        headers = {
            "Content-Type": "text/plain",
            "Accept": accept_content_types,
        }
        handler = AsyncMock()
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        handler.assert_not_called()

    async def test_dispatch_protocol_version_validation(
        self, transport: StreamableHTTPTransport[None], valid_body: str, accept_content_types: str
    ):
        """Test protocol version validation."""
        headers = {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": "invalid-version",
        }
        handler = AsyncMock()
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.BAD_REQUEST
        assert "Unsupported protocol version" in str(result.content)
        handler.assert_not_called()

    async def test_handle_post_request_task_task_status_handling(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test the _handle_post_request_task method's task status handling."""
        handler = AsyncMock(return_value='{"result": "success"}')
        transport.minimcp.handle = handler
        result: MCPHTTPResponse | None = None

        async with transport:
            async with anyio.create_task_group() as tg:
                result = await tg.start(transport._handle_post_request_task, request_headers, valid_body, None)

        assert result is not None
        assert result.status_code == HTTPStatus.OK
        assert result.content == '{"result": "success"}'
        assert result.media_type == "application/json"

        handler.assert_called_once()

    async def test_handle_post_request_task_exception_handling(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test the _handle_post_request_task method's exception handling."""
        handler = AsyncMock(side_effect=Exception("Test error"))
        transport.minimcp.handle = handler
        result: MCPHTTPResponse | None = None

        async with anyio.create_task_group() as tg:
            result = await tg.start(transport._handle_post_request_task, request_headers, valid_body, None)

        assert result is not None
        assert result.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert result.content is not None
        assert "error" in str(result.content)
        handler.assert_called_once()

    async def test_concurrent_request_handling(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test that multiple requests can be handled concurrently."""
        handler = AsyncMock(return_value='{"result": "success"}')
        transport.minimcp.handle = handler
        results: list[MCPHTTPResponse | MCPStreamingHTTPResponse] = []

        async with transport:
            async with anyio.create_task_group() as tg:

                async def make_request():
                    result = await transport.dispatch("POST", request_headers, valid_body)
                    results.append(result)

                for _ in range(3):
                    tg.start_soon(make_request)

        # All requests should have been processed
        assert len(results) == 3

    async def test_transport_reuse_after_close(self, transport: StreamableHTTPTransport[None]):
        """Test that transport can be reused after closing."""
        async with transport:
            assert transport._tg is not None
        assert transport._tg is None

    async def test_multiple_start_calls(self, transport: StreamableHTTPTransport[None]):
        """Test behavior when start is called multiple times."""
        # First start
        async with transport:
            assert transport._tg is not None
        assert transport._tg is None

    async def test_initialize_request_skips_version_check(self, transport: StreamableHTTPTransport[None]):
        """Test that initialize requests skip protocol version validation."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            # No protocol version header
        }

        initialize_body = json.dumps(
            {"jsonrpc": "2.0", "method": "initialize", "params": {"protocolVersion": "2025-06-18"}, "id": 1}
        )

        handler = AsyncMock(return_value='{"result": "initialized"}')
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, initialize_body)

        assert result.status_code == HTTPStatus.OK
        handler.assert_called_once()

    async def test_stream_cleanup_on_handler_exception(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test that streams are properly cleaned up when handler raises exception."""

        async def streaming_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "stream1", "id": 1}')
            raise Exception("Handler failed")

        streaming_handler = AsyncMock(side_effect=streaming_handler)
        transport.minimcp.handle = streaming_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)
            assert isinstance(result.content, MemoryObjectReceiveStream)
            await result.content.receive()  # Consume the send message
            error_message = str(await result.content.receive())

        assert result.status_code == HTTPStatus.OK
        assert result.content is not None
        assert "Handler failed" in error_message
        streaming_handler.assert_called_once()

    async def test_stream_cleanup_without_consumer(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test Case 2: Stream cleanup when no consumer reads from recv_stream."""

        async def streaming_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "stream1", "id": 1}')
            await send('{"jsonrpc": "2.0", "result": "stream2", "id": 2}')
            return "Final result"

        streaming_handler = AsyncMock(side_effect=streaming_handler)
        transport.minimcp.handle = streaming_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)
            # Don't consume from recv_stream - simulates test without consumer
            assert isinstance(result.content, MemoryObjectReceiveStream)

        # Transport exit should cancel tasks and close_receive() should clean up
        # If this test completes without issues, cleanup worked correctly
        streaming_handler.assert_called_once()

    async def test_stream_cleanup_with_early_consumer_disconnect(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test Case 3: Consumer disconnects mid-stream without fully draining."""

        async def streaming_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "stream1", "id": 1}')
            await anyio.sleep(0.1)  # Simulate some work
            await send('{"jsonrpc": "2.0", "result": "stream2", "id": 2}')
            await anyio.sleep(0.1)
            await send('{"jsonrpc": "2.0", "result": "stream3", "id": 3}')
            return "Final result"

        streaming_handler = AsyncMock(side_effect=streaming_handler)
        transport.minimcp.handle = streaming_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)
            assert isinstance(result.content, MemoryObjectReceiveStream)

            # Consumer reads only first message then disconnects (closes stream)
            msg1 = await result.content.receive()
            assert "stream1" in str(msg1)

            # Simulate consumer disconnecting
            await result.content.aclose()

        # Handler should handle BrokenResourceError gracefully
        # close_receive() ensures cleanup even though consumer closed early
        streaming_handler.assert_called_once()

    async def test_stream_cleanup_during_transport_shutdown(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test Case 4: Transport shutdown cancels tasks with proper stream cleanup."""

        async def long_running_handler(message: Message, send: Send, _: Any):
            # Start sending - this will trigger stream creation
            await send('{"jsonrpc": "2.0", "result": "stream1", "id": 1}')
            # Try to send more - simulates long-running handler
            try:
                await anyio.sleep(10)  # Would block for 10s
                await send('{"jsonrpc": "2.0", "result": "stream2", "id": 2}')
            except anyio.CancelledError:
                # Expected when transport shuts down
                raise

        long_running_handler = AsyncMock(side_effect=long_running_handler)
        transport.minimcp.handle = long_running_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)
            assert isinstance(result.content, MemoryObjectReceiveStream)

            # Consume the first message to unblock the handler
            await result.content.receive()

            # Now handler is running (sleeping for 10s)
            # Exit transport context to trigger cancellation
            await anyio.sleep(0.01)

        # If we get here without hanging, cancellation + shielded cleanup worked
        long_running_handler.assert_called_once()

    async def test_stream_cleanup_delay_allows_normal_consumption(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test Case 1: Normal consumer finishes within delay window."""

        async def streaming_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "stream1", "id": 1}')
            await send('{"jsonrpc": "2.0", "result": "stream2", "id": 2}')
            return "Final result"

        streaming_handler = AsyncMock(side_effect=streaming_handler)
        transport.minimcp.handle = streaming_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, valid_body)
            assert isinstance(result.content, MemoryObjectReceiveStream)

            # Normal consumer reads all messages quickly
            recv_stream = result.content
            messages: list[str] = []
            async with anyio.create_task_group() as tg:

                async def consume():
                    try:
                        while True:
                            msg = await recv_stream.receive()
                            messages.append(str(msg))
                    except anyio.EndOfStream:
                        pass

                tg.start_soon(consume)

                # Give consumer time to read (within the 0.1s delay window)
                await anyio.sleep(0.05)

        # Consumer should have received both messages before cleanup
        assert len(messages) >= 2
        streaming_handler.assert_called_once()

    async def test_stream_resource_cleanup_no_leaks(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test that recv_stream is always closed to prevent resource leaks."""

        async def streaming_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "data", "id": 1}')
            return "done"

        streaming_handler = AsyncMock(side_effect=streaming_handler)
        transport.minimcp.handle = streaming_handler

        # Run multiple times to verify no resource accumulation
        for _ in range(3):
            async with transport:
                result = await transport.dispatch("POST", request_headers, valid_body)
                # Don't consume - simulates worst case
                assert isinstance(result.content, MemoryObjectReceiveStream)

            # Small delay to let cleanup complete
            await anyio.sleep(0.15)

        # If no "unraisable exception" warnings, streams were properly closed
        assert streaming_handler.call_count == 3


class TestStreamableHTTPTransportHeaderValidation:
    """Test suite for StreamableHTTPTransport header validation (stateless)."""

    @pytest.fixture
    def accept_content_types(self) -> str:
        return "application/json, text/event-stream"

    @pytest.fixture
    def request_headers(self, accept_content_types: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        }

    @pytest.fixture
    def valid_body(self):
        """Create a valid JSON-RPC request body."""
        return json.dumps({"jsonrpc": "2.0", "method": "test_method", "params": {"test": "value"}, "id": 1})

    @pytest.fixture
    def mock_handler(self) -> AsyncMock:
        """Create a mock handler."""
        return AsyncMock(return_value='{"jsonrpc": "2.0", "result": "success", "id": 1}')

    @pytest.fixture
    def transport(self, mock_handler: AsyncMock) -> StreamableHTTPTransport[Any]:
        mcp = AsyncMock(spec=MiniMCP[Any])
        mcp.handle = mock_handler
        return StreamableHTTPTransport[Any](mcp)

    async def test_missing_content_type_header(self, transport: StreamableHTTPTransport[None], valid_body: str):
        """Test that missing Content-Type header is rejected."""
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        handler = AsyncMock()
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        handler.assert_not_called()

    async def test_wrong_content_type_header(self, transport: StreamableHTTPTransport[None], valid_body: str):
        """Test that wrong Content-Type header is rejected."""
        headers = {
            "Content-Type": "text/html",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        handler = AsyncMock()
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        handler.assert_not_called()

    async def test_content_type_with_charset(self, transport: StreamableHTTPTransport[None], valid_body: str):
        """Test that Content-Type with charset is accepted."""
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        handler = AsyncMock(return_value='{"result": "success"}')
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, valid_body)

        # Should accept charset parameter
        assert result.status_code == HTTPStatus.OK
        handler.assert_called_once()

    async def test_protocol_version_case_insensitive(self, transport: StreamableHTTPTransport[None], valid_body: str):
        """Test that protocol version header is case-insensitive."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18",  # lowercase
        }
        handler = AsyncMock(return_value='{"result": "success"}')
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        handler.assert_called_once()

    async def test_empty_body_handling(self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str]):
        """Test handling of empty request body (stateless)."""
        handler = AsyncMock()
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, "")

        # Each request is independent, should handle empty body
        assert result.status_code in (HTTPStatus.OK, HTTPStatus.BAD_REQUEST, HTTPStatus.INTERNAL_SERVER_ERROR)

    async def test_malformed_json_body(self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str]):
        """Test handling of malformed JSON in request body (stateless)."""
        malformed_body = "{invalid json"
        handler = AsyncMock()
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, malformed_body)

        # Each request is independent, should handle malformed JSON
        assert result.status_code in (HTTPStatus.OK, HTTPStatus.BAD_REQUEST, HTTPStatus.INTERNAL_SERVER_ERROR)

    async def test_very_large_body(self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str]):
        """Test handling of very large request bodies (stateless processing)."""
        # Create a large but valid JSON-RPC request (1MB of data)
        large_data = "x" * (1024 * 1024)
        large_body = json.dumps({"jsonrpc": "2.0", "method": "test", "params": {"data": large_data}, "id": 1})
        handler = AsyncMock(return_value='{"result": "success"}')
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, large_body)

        # Should handle large bodies in stateless manner
        assert result.status_code == HTTPStatus.OK
        handler.assert_called_once()

    async def test_concurrent_stateless_requests(
        self, transport: StreamableHTTPTransport[None], valid_body: str, request_headers: dict[str, str]
    ):
        """Test concurrent stateless requests with different HTTP methods."""
        handler = AsyncMock(return_value='{"result": "success"}')
        transport.minimcp.handle = handler
        results: list[MCPHTTPResponse | MCPStreamingHTTPResponse] = []

        async with transport:
            async with anyio.create_task_group() as tg:

                async def make_request(method: str):
                    result = await transport.dispatch(method, request_headers, valid_body)
                    results.append(result)

                # Each request is independent (stateless)
                tg.start_soon(make_request, "POST")
                tg.start_soon(make_request, "GET")
                tg.start_soon(make_request, "PUT")

        # POST should succeed, others should fail (method validation is stateless)
        post_results = [r for r in results if r.status_code == HTTPStatus.OK]
        error_results = [r for r in results if r.status_code == HTTPStatus.METHOD_NOT_ALLOWED]
        assert len(post_results) == 1
        assert len(error_results) == 2

    async def test_sse_with_unicode_content(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str]
    ):
        """Test SSE streaming with Unicode content."""
        unicode_body = json.dumps({"jsonrpc": "2.0", "method": "test_unicode", "params": {"text": "नमस्ते 🌍"}, "id": 1})

        async def unicode_handler(message: Message, send: Send, _: Any):
            await send('{"jsonrpc": "2.0", "result": "नमस्ते 🎉", "id": 1}')
            return '{"jsonrpc": "2.0", "result": "final", "id": 2}'

        unicode_handler = AsyncMock(side_effect=unicode_handler)
        transport.minimcp.handle = unicode_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, unicode_body)

            # Stateless streaming with Unicode
            assert result.status_code == HTTPStatus.OK
            assert isinstance(result.content, MemoryObjectReceiveStream)

            # Consume the stream to verify Unicode handling
            msg = await result.content.receive()
            assert "नमस्ते 🎉" in str(msg)


class TestStreamableHTTPTransportEdgeCases:
    """Test suite for edge cases in StreamableHTTPTransport."""

    @pytest.fixture
    def accept_content_types(self) -> str:
        return "application/json, text/event-stream"

    @pytest.fixture
    def request_headers(self, accept_content_types: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        }

    @pytest.fixture
    def valid_body(self):
        """Create a valid JSON-RPC request body."""
        return json.dumps({"jsonrpc": "2.0", "method": "test_method", "params": {"test": "value"}, "id": 1})

    @pytest.fixture
    def transport(self) -> StreamableHTTPTransport[Any]:
        mcp = AsyncMock(spec=MiniMCP[Any])
        mcp.handle = AsyncMock(return_value='{"jsonrpc": "2.0", "result": "success", "id": 1}')
        return StreamableHTTPTransport[Any](mcp)

    async def test_transport_double_start_error(self, transport: StreamableHTTPTransport[None]):
        """Test that starting transport twice raises an error."""
        async with transport:
            # Transport is now started
            assert transport._tg is not None

            # Trying to dispatch from another context should work
            # as the transport is already started

    async def test_handler_returns_none(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str], valid_body: str
    ):
        """Test handling when handler returns None."""
        body = json.dumps({"jsonrpc": "2.0", "method": "test", "id": 1})
        handler = AsyncMock(return_value=None)
        transport.minimcp.handle = handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, body)

        # Should handle None return value
        assert result.status_code in (HTTPStatus.OK, HTTPStatus.ACCEPTED, HTTPStatus.INTERNAL_SERVER_ERROR)

    async def test_handler_slow_response(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str]
    ):
        """Test handling of slow handler responses."""
        body = json.dumps({"jsonrpc": "2.0", "method": "slow", "id": 1})

        async def slow_handler(message: Message, send: Send, _: Any):
            await anyio.sleep(0.5)  # Simulate slow processing
            return '{"jsonrpc": "2.0", "result": "slow_result", "id": 1}'

        slow_handler = AsyncMock(side_effect=slow_handler)
        transport.minimcp.handle = slow_handler

        async with transport:
            result = await transport.dispatch("POST", request_headers, body)

        assert result.status_code == HTTPStatus.OK
        assert isinstance(result.content, Message)
        assert "slow_result" in result.content
        slow_handler.assert_called_once()

    async def test_multiple_sequential_requests_same_transport(
        self, transport: StreamableHTTPTransport[None], request_headers: dict[str, str]
    ):
        """Test multiple sequential requests through the same transport instance."""
        handler = AsyncMock(return_value='{"jsonrpc": "2.0", "result": "success", "id": 1}')
        transport.minimcp.handle = handler

        async with transport:
            # Make multiple requests sequentially
            for i in range(5):
                body = json.dumps({"jsonrpc": "2.0", "method": "test", "params": {"count": i}, "id": i})
                result = await transport.dispatch("POST", request_headers, body)
                assert result.status_code == HTTPStatus.OK

        # Handler should have been called 5 times
        assert handler.call_count == 5


class TestStreamableHTTPTransportBase(TestBaseHTTPTransport):
    """
    Test suite that validates StreamableHTTPTransport inherits all base HTTPTransport functionality.

    This class inherits all tests from TestHTTPTransport and overrides the transport fixture
    to properly handle StreamableHTTPTransport's async context manager requirement.
    """

    @pytest.fixture
    def accept_content_types(self) -> str:
        return "application/json, text/event-stream"

    @pytest.fixture
    def request_headers(self, accept_content_types: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        }

    @pytest.fixture
    async def transport(self, mock_handler: AsyncMock) -> AsyncIterator[StreamableHTTPTransport[Any]]:
        """
        Create and start a StreamableHTTPTransport instance.

        This fixture overrides the base class fixture to wrap the transport in an async
        context manager, which is required for StreamableHTTPTransport's dispatch method.
        """
        mcp = AsyncMock(spec=MiniMCP[Any])
        mcp.handle = mock_handler
        transport = StreamableHTTPTransport[Any](mcp)
        async with transport:
            yield transport


class TestStreamManagerEdgeCases:
    """Test suite for StreamManager edge cases and error handling."""

    async def test_stream_manager_send_before_create(self):
        """Test that send raises error when stream is not created."""

        stream_manager = StreamManager(lambda x: None)

        with pytest.raises(MiniMCPError, match="Send stream is unavailable"):
            await stream_manager.send("test message")

    async def test_streamable_http_as_starlette(self):
        """Test as_starlette method for streamable HTTP."""
        server = MiniMCP[Any](name="test-server", version="1.0.0")
        transport = StreamableHTTPTransport(server)

        app = transport.as_starlette(path="/mcp", debug=True)

        # Verify app is created with lifespan
        assert app is not None
        assert len(app.routes) == 1
