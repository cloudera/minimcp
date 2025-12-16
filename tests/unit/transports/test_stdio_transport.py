"""Comprehensive stdio transport tests."""

from typing import Any
from unittest.mock import AsyncMock

import anyio
import pytest

from minimcp.exceptions import InvalidMessageError
from minimcp.minimcp import MiniMCP
from minimcp.transports.stdio import StdioTransport
from minimcp.types import NoMessage, Send

pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_stdout() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_stdin() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def stdio_transport(mock_stdin: AsyncMock, mock_stdout: AsyncMock) -> StdioTransport[Any]:
    mcp = AsyncMock(spec=MiniMCP[Any])
    return StdioTransport[Any](mcp, mock_stdin, mock_stdout)


@pytest.fixture(autouse=True)
async def timeout_5s():
    """Fail test if it takes longer than 5 seconds."""
    with anyio.fail_after(5):
        yield


class TestWriteMsg:
    """Test suite for write_msg function."""

    async def test__write_msg_with_message(self, stdio_transport: StdioTransport[Any], mock_stdout: AsyncMock):
        """Test _write_msg writes message to stdout."""
        message = '{"jsonrpc":"2.0","id":1,"result":"test"}'
        await stdio_transport.write_msg(message)

        # Should write message with newline
        mock_stdout.write.assert_called_once_with(message + "\n")

    async def test__write_msg_rejects_embedded_newline(self, stdio_transport: StdioTransport[Any]):
        """Test _write_msg rejects messages with embedded newlines per MCP spec."""
        message_with_newline = '{"jsonrpc":"2.0",\n"id":1}'

        with pytest.raises(ValueError, match="Messages MUST NOT contain embedded newlines"):
            await stdio_transport.write_msg(message_with_newline)

    async def test__write_msg_rejects_embedded_carriage_return(self, stdio_transport: StdioTransport[Any]):
        """Test _write_msg rejects messages with embedded carriage returns per MCP spec."""
        message_with_cr = '{"jsonrpc":"2.0",\r"id":1}'

        with pytest.raises(ValueError, match="Messages MUST NOT contain embedded newlines"):
            await stdio_transport.write_msg(message_with_cr)

    async def test__write_msg_rejects_embedded_crlf(self, stdio_transport: StdioTransport[Any], mock_stdout: AsyncMock):
        """Test _write_msg rejects messages with embedded CRLF sequences per MCP spec."""
        message_with_crlf = '{"jsonrpc":"2.0",\r\n"id":1}'

        with pytest.raises(ValueError, match="Messages MUST NOT contain embedded newlines"):
            await stdio_transport.write_msg(message_with_crlf)

        # Should not write anything
        mock_stdout.write.assert_not_called()

    async def test__write_msg_accepts_message_without_embedded_newlines(
        self, stdio_transport: StdioTransport[Any], mock_stdout: AsyncMock
    ):
        """Test _write_msg accepts valid messages without embedded newlines."""
        valid_message = '{"jsonrpc":"2.0","id":1,"method":"test","params":{"key":"value"}}'

        await stdio_transport.write_msg(valid_message)

        # Should write message with trailing newline
        mock_stdout.write.assert_called_once_with(valid_message + "\n")


class TestDispatch:
    """Test suite for dispatch function."""

    async def test_dispatch_with_valid_input(self, stdio_transport: StdioTransport[Any], mock_stdout: AsyncMock):
        """Test dispatch processes valid input."""
        handler = AsyncMock(return_value='{"result":"success"}')
        stdio_transport.minimcp.handle = handler

        # dispatch receives already-stripped line from transport()
        await stdio_transport.dispatch('{"jsonrpc":"2.0","method":"test"}')

        # Handler should be called with line and write callback
        handler.assert_called_once()
        call_args = handler.call_args[0]
        assert call_args[0] == '{"jsonrpc":"2.0","method":"test"}'
        assert callable(call_args[1])

        # Response should be written
        mock_stdout.write.assert_called_once_with('{"result":"success"}\n')

    async def test_dispatch_passes_line_as_is(self, stdio_transport: StdioTransport[Any]):
        """Test dispatch passes line to handler as-is."""
        handler = AsyncMock(return_value='{"result":"ok"}')
        stdio_transport.minimcp.handle = handler

        # The transport() strips, but dispatch doesn't
        test_line = '{"test":1}'
        await stdio_transport.dispatch(test_line)

        # Line should be passed as-is
        call_args = handler.call_args[0]
        assert call_args[0] == test_line

    async def test_dispatch_always_calls_handler(self, stdio_transport: StdioTransport[Any]):
        """Test dispatch always calls handler (empty check is in transport)."""
        handler = AsyncMock(return_value='{"ok":true}')
        stdio_transport.minimcp.handle = handler

        # dispatch doesn't check for empty - that's in transport()
        await stdio_transport.dispatch("test")

        # Handler should be called
        handler.assert_called_once()

    async def test_dispatch_with_non_message_response(
        self, stdio_transport: StdioTransport[Any], mock_stdout: AsyncMock
    ):
        """Test dispatch handles NoMessage return."""
        handler = AsyncMock(return_value=NoMessage.NOTIFICATION)
        stdio_transport.minimcp.handle = handler

        await stdio_transport.dispatch('{"method":"notify"}')

        # Handler should be called
        handler.assert_called_once()

        # write should NOT be called for NoMessage (checked with isinstance)
        mock_stdout.write.assert_not_called()


class TestRun:
    """Test suite for stdio transport function."""

    async def test_run_relays_single_message(
        self, stdio_transport: StdioTransport[Any], mock_stdin: AsyncMock, mock_stdout: AsyncMock
    ):
        """Test transport relays a single message through handler."""
        # Create mock stdin with one message
        input_message = '{"jsonrpc":"2.0","id":1,"method":"test"}\n'
        mock_stdin.__aiter__.return_value = iter([input_message])

        # Create handler that echoes back
        received_messages: list[str] = []

        async def echo_handler(message: str, _: Send):
            received_messages.append(message)
            response: str = f'{{"echo":"{message}"}}'
            return response

        stdio_transport.minimcp.handle = AsyncMock(side_effect=echo_handler)

        await stdio_transport.run()

        # Handler should have received the message
        assert len(received_messages) == 1
        assert received_messages[0] == '{"jsonrpc":"2.0","id":1,"method":"test"}'

        # Response should be written to stdout
        assert mock_stdout.write.call_count >= 1

    async def test_run_relays_multiple_messages(
        self, stdio_transport: StdioTransport[Any], mock_stdin: AsyncMock, mock_stdout: AsyncMock
    ):
        """Test transport relays multiple messages."""
        input_messages = [
            '{"jsonrpc":"2.0","id":1,"method":"test1"}\n',
            '{"jsonrpc":"2.0","id":2,"method":"test2"}\n',
            '{"jsonrpc":"2.0","id":3,"method":"test3"}\n',
        ]
        mock_stdin.__aiter__.return_value = iter(input_messages)

        received_messages: list[str] = []

        async def collecting_handler(message: str, send: Send):
            received_messages.append(message)
            return f'{{"id":{len(received_messages)}}}'

        stdio_transport.minimcp.handle = AsyncMock(side_effect=collecting_handler)

        await stdio_transport.run()

        # All messages should be received
        assert len(received_messages) == 3
        assert '{"jsonrpc":"2.0","id":1,"method":"test1"}' in received_messages
        assert '{"jsonrpc":"2.0","id":2,"method":"test2"}' in received_messages
        assert '{"jsonrpc":"2.0","id":3,"method":"test3"}' in received_messages

    async def test_transport_handler_can_use_send_callback(
        self, stdio_transport: StdioTransport[Any], mock_stdin: AsyncMock, mock_stdout: AsyncMock
    ):
        """Test handler can use send callback to write intermediate messages."""
        input_message = '{"jsonrpc":"2.0","id":1,"method":"test"}\n'
        mock_stdin.__aiter__.return_value = iter([input_message])

        sent_messages: list[str] = []

        async def handler_with_callback(message: str, send: Send):
            # Send intermediate message
            await send('{"progress":"50%"}')
            sent_messages.append('{"progress":"50%"}')
            # Return final response
            return '{"result":"done"}'

        stdio_transport.minimcp.handle = AsyncMock(side_effect=handler_with_callback)

        await stdio_transport.run()

        # Handler should have sent intermediate message
        assert len(sent_messages) == 1
        # stdout.write should be called for both intermediate and final
        assert mock_stdout.write.call_count >= 2

    async def test_transport_skips_empty_lines(
        self, stdio_transport: StdioTransport[Any], mock_stdin: AsyncMock, mock_stdout: AsyncMock
    ):
        """Test transport skips empty lines."""
        input_messages = [
            '{"jsonrpc":"2.0","id":1,"method":"test"}\n',
            "   \n",  # Empty line
            "\n",  # Just newline
            '{"jsonrpc":"2.0","id":2,"method":"test2"}\n',
        ]
        mock_stdin.__aiter__.return_value = iter(input_messages)

        received_messages: list[str] = []

        async def collecting_handler(message: str, _: Send):
            received_messages.append(message)
            return '{"ok":true}'

        stdio_transport.minimcp.handle = AsyncMock(side_effect=collecting_handler)

        await stdio_transport.run()

        # Only non-empty messages should be received
        assert len(received_messages) == 2

    async def test_transport_concurrent_message_handling(
        self, stdio_transport: StdioTransport[Any], mock_stdin: AsyncMock, mock_stdout: AsyncMock
    ):
        """Test transport handles messages concurrently."""

        # Messages that will be processed
        input_messages = [
            '{"jsonrpc":"2.0","id":1,"method":"slow"}\n',
            '{"jsonrpc":"2.0","id":2,"method":"fast"}\n',
        ]
        mock_stdin.__aiter__.return_value = iter(input_messages)

        completed_order: list[str] = []

        async def concurrent_handler(message: str, _: Send):
            msg_id = "1" if 'id":1' in message else "2"
            # Simulate slow message 1, fast message 2
            if msg_id == "1":
                await anyio.sleep(0.1)
            completed_order.append(msg_id)
            return f'{{"id":{msg_id}}}'

        stdio_transport.minimcp.handle = AsyncMock(side_effect=concurrent_handler)

        await stdio_transport.run()

        # Fast message should complete before slow message
        assert len(completed_order) == 2
        # Message 2 (fast) should complete first
        assert completed_order[0] == "2"
        assert completed_order[1] == "1"

    async def test_transport_handler_returns_no_message(
        self, stdio_transport: StdioTransport[Any], mock_stdin: AsyncMock, mock_stdout: AsyncMock
    ):
        """Test transport handles NoMessage return from handler."""
        input_message = '{"jsonrpc":"2.0","method":"notify"}\n'
        mock_stdin.__aiter__.return_value = iter([input_message])

        async def notification_handler(message: str, send: Send):
            # Return NoMessage for notifications
            return NoMessage.NOTIFICATION

        stdio_transport.minimcp.handle = AsyncMock(side_effect=notification_handler)

        await stdio_transport.run()

        # write should not be called for NoMessage
        # (dispatch checks isinstance and skips)
        assert mock_stdout.write.call_count == 0

    async def test_dispatch_with_invalid_message_error(
        self, stdio_transport: StdioTransport[Any], mock_stdout: AsyncMock
    ):
        """Test dispatch when InvalidMessageError is raised."""

        error_response = '{"jsonrpc":"2.0","error":{"code":-32600,"message":"Invalid Request"},"id":1}'
        stdio_transport.minimcp.handle = AsyncMock(side_effect=InvalidMessageError("Invalid", error_response))

        await stdio_transport.dispatch('{"jsonrpc":"2.0","id":1,"method":"test"}')

        # Should write the error response
        mock_stdout.write.assert_called_once_with(error_response + "\n")

    async def test_dispatch_with_unexpected_exception(
        self, stdio_transport: StdioTransport[Any], mock_stdout: AsyncMock
    ):
        """Test dispatch when an unexpected exception is raised."""
        stdio_transport.minimcp.handle = AsyncMock(side_effect=RuntimeError("Unexpected error"))

        await stdio_transport.dispatch('{"jsonrpc":"2.0","id":1,"method":"test"}')

        # Should write an error response
        assert mock_stdout.write.call_count == 1
        written_message = mock_stdout.write.call_args[0][0]
        assert "error" in written_message
        assert "Unexpected error" in written_message or "INTERNAL_ERROR" in written_message
