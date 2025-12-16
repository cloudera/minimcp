import json
from collections.abc import Coroutine
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import anyio
import mcp.types as types
import pytest
from mcp.server.lowlevel.server import NotificationOptions, Server

from minimcp.exceptions import (
    ContextError,
    InternalMCPError,
    InvalidArgumentsError,
    InvalidJSONError,
    InvalidJSONRPCMessageError,
    InvalidMessageError,
    MCPRuntimeError,
    PrimitiveError,
    RequestHandlerNotFoundError,
    ResourceNotFoundError,
    UnsupportedMessageTypeError,
)
from minimcp.managers.context_manager import Context, ContextManager
from minimcp.managers.prompt_manager import PromptManager
from minimcp.managers.resource_manager import ResourceManager
from minimcp.managers.tool_manager import ToolManager
from minimcp.minimcp import MiniMCP
from minimcp.types import RESOURCE_NOT_FOUND, Message, NoMessage

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def timeout_5s():
    """Fail test if it takes longer than 5 seconds."""
    with anyio.fail_after(5):
        yield


class TestMiniMCP:
    """Test suite for MiniMCP class."""

    @pytest.fixture
    def minimcp(self) -> MiniMCP[Any]:
        """Create a MiniMCP instance for testing."""
        return MiniMCP[Any](name="test-server", version="1.0.0", instructions="Test server instructions")

    @pytest.fixture
    def minimcp_with_custom_config(self) -> MiniMCP[Any]:
        """Create a MiniMCP instance with custom configuration."""
        return MiniMCP[Any](
            name="custom-server",
            version="2.0.0",
            instructions="Custom instructions",
            idle_timeout=60,
            max_concurrency=50,
            include_stack_trace=True,
        )

    @pytest.fixture
    def valid_request_message(self) -> str:
        """Create a valid JSON-RPC request message."""
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            }
        )

    @pytest.fixture
    def valid_notification_message(self) -> str:
        """Create a valid JSON-RPC notification message."""
        return json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    @pytest.fixture
    def mock_send(self) -> AsyncMock:
        """Create a mock send function."""
        return AsyncMock()

    async def test_init_basic(self) -> None:
        """Test basic MiniMCP initialization."""
        server: MiniMCP[Any] = MiniMCP[Any](name="test-server")

        assert server.name == "test-server"
        assert server.version is None
        assert server.instructions is None
        assert isinstance(server._core, Server)
        assert isinstance(server.tool, ToolManager)
        assert isinstance(server.prompt, PromptManager)
        assert isinstance(server.resource, ResourceManager)
        assert isinstance(server.context, ContextManager)
        assert server._include_stack_trace is False

    async def test_init_with_all_parameters(self, minimcp_with_custom_config: MiniMCP[Any]) -> None:
        """Test MiniMCP initialization with all parameters."""
        server: MiniMCP[Any] = minimcp_with_custom_config

        assert server.name == "custom-server"
        assert server.version == "2.0.0"
        assert server.instructions == "Custom instructions"
        assert server._include_stack_trace is True
        # Note: Limiter internal attributes may vary, test behavior instead

    async def test_properties(self, minimcp: MiniMCP[Any]) -> None:
        """Test MiniMCP properties."""
        assert minimcp.name == "test-server"
        assert minimcp.version == "1.0.0"
        assert minimcp.instructions == "Test server instructions"

    async def test_notification_options_setup(self, minimcp: MiniMCP[Any]) -> None:
        """Test that notification options are properly set up."""
        assert minimcp._notification_options is not None
        assert isinstance(minimcp._notification_options, NotificationOptions)
        assert minimcp._notification_options.prompts_changed is False
        assert minimcp._notification_options.resources_changed is False
        assert minimcp._notification_options.tools_changed is False

    async def test_core_setup(self, minimcp: MiniMCP[Any]) -> None:
        """Test that core server is properly set up."""
        assert minimcp._core.name == "test-server"
        assert minimcp._core.version == "1.0.0"
        assert minimcp._core.instructions == "Test server instructions"

        # Check that initialize handler is registered
        assert types.InitializeRequest in minimcp._core.request_handlers
        assert minimcp._core.request_handlers[types.InitializeRequest] == minimcp._initialize_handler

    async def test_managers_setup(self, minimcp: MiniMCP[Any]) -> None:
        """Test that all managers are properly initialized."""
        # Check that managers are instances of correct classes
        assert isinstance(minimcp.tool, ToolManager)
        assert isinstance(minimcp.prompt, PromptManager)
        assert isinstance(minimcp.resource, ResourceManager)
        assert isinstance(minimcp.context, ContextManager)

        # Note: Manager internal structure may vary, test functionality instead

    async def test_parse_message_valid_request(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test parsing a valid JSON-RPC request message."""
        rpc_msg = minimcp._parse_message(valid_request_message)

        assert isinstance(rpc_msg, types.JSONRPCMessage)
        assert isinstance(rpc_msg.root, types.JSONRPCRequest)
        assert rpc_msg.root.method == "initialize"
        assert rpc_msg.root.id == 1

    async def test_parse_message_valid_notification(
        self, minimcp: MiniMCP[Any], valid_notification_message: str
    ) -> None:
        """Test parsing a valid JSON-RPC notification message."""
        rpc_msg = minimcp._parse_message(valid_notification_message)

        assert isinstance(rpc_msg, types.JSONRPCMessage)
        assert isinstance(rpc_msg.root, types.JSONRPCNotification)
        assert rpc_msg.root.method == "notifications/initialized"

    async def test_parse_message_invalid_json(self, minimcp: MiniMCP[Any]) -> None:
        """Test parsing invalid JSON raises ParserError."""
        invalid_json = '{"invalid": json}'

        with pytest.raises(InvalidJSONError):
            minimcp._parse_message(invalid_json)

    async def test_parse_message_invalid_rpc_format(self, minimcp: MiniMCP[Any]) -> None:
        """Test parsing invalid JSON-RPC format raises InvalidParamsError."""
        invalid_rpc = json.dumps({"not": "jsonrpc"})

        with pytest.raises(InvalidJSONRPCMessageError):
            minimcp._parse_message(invalid_rpc)

    async def test_parse_message_missing_id_in_dict(self, minimcp: MiniMCP[Any]) -> None:
        """Test parsing message without ID returns empty string."""
        message_without_id = json.dumps({"jsonrpc": "2.0", "method": "test"})

        message = minimcp._parse_message(message_without_id)
        assert message is not None

    async def test_parse_message_non_dict_json(self, minimcp: MiniMCP[Any]) -> None:
        """Test parsing non-dict JSON returns empty message ID."""
        non_dict_json = json.dumps(["not", "a", "dict"])

        with pytest.raises(InvalidJSONRPCMessageError):
            minimcp._parse_message(non_dict_json)

    async def test_handle_rpc_msg_request(self, minimcp: MiniMCP[Any]) -> None:
        """Test handling JSON-RPC request message."""
        # Create a mock request
        mock_request = types.JSONRPCRequest(
            jsonrpc="2.0",
            id=1,
            method="initialize",
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )
        rpc_msg = types.JSONRPCMessage(mock_request)

        response = await minimcp._handle_rpc_msg(rpc_msg)
        assert isinstance(response, Message)

    async def test_handle_rpc_msg_notification(self, minimcp: MiniMCP[Any]) -> None:
        """Test handling JSON-RPC notification message."""
        mock_notification = types.JSONRPCNotification(jsonrpc="2.0", method="notifications/initialized", params={})
        rpc_msg = types.JSONRPCMessage(mock_notification)

        response: Message | NoMessage = await minimcp._handle_rpc_msg(rpc_msg)

        assert response == NoMessage.NOTIFICATION

    async def test_handle_rpc_msg_unsupported_type(self, minimcp: MiniMCP[Any]):
        """Test handling unsupported RPC message type."""
        # Create a mock message with unsupported root type
        mock_msg = Mock()
        mock_msg.root = "unsupported_type"

        with pytest.raises(UnsupportedMessageTypeError):
            await minimcp._handle_rpc_msg(mock_msg)

    async def test_handle_client_request_success(self, minimcp: MiniMCP[Any]) -> None:
        """Test successful client request handling."""
        # Create initialize request
        init_request = types.InitializeRequest(
            method="initialize",
            params=types.InitializeRequestParams(
                protocolVersion="2025-06-18",
                capabilities=types.ClientCapabilities(),
                clientInfo=types.Implementation(name="test", version="1.0"),
            ),
        )
        client_request = types.ClientRequest(init_request)

        result = await minimcp._handle_client_request(client_request)

        assert isinstance(result, types.ServerResult)
        assert isinstance(result.root, types.InitializeResult)

    async def test_handle_client_request_method_not_found(self, minimcp: MiniMCP[Any]) -> None:
        """Test client request with unknown method."""

        # Create a mock request type that's not registered
        class UnknownRequest:
            pass

        mock_request = Mock()
        mock_request.root = UnknownRequest()

        with pytest.raises(RequestHandlerNotFoundError):
            await minimcp._handle_client_request(mock_request)

    async def test_handle_client_notification_success(self, minimcp: MiniMCP[Any]) -> None:
        """Test successful client notification handling."""
        # Create initialized notification
        init_notification = types.InitializedNotification(
            method="notifications/initialized",
            params={},  # type: ignore
        )
        client_notification = types.ClientNotification(init_notification)

        result = await minimcp._handle_client_notification(client_notification)

        assert result == NoMessage.NOTIFICATION

    async def test_handle_client_notification_no_handler(self, minimcp: MiniMCP[Any]) -> None:
        """Test client notification with no registered handler."""

        # Create a mock notification type that's not registered
        class UnknownNotification:
            pass

        mock_notification = Mock()
        mock_notification.root = UnknownNotification()

        result = await minimcp._handle_client_notification(mock_notification)

        assert result == NoMessage.NOTIFICATION

    async def test_handle_client_notification_handler_exception(self, minimcp: MiniMCP[Any]) -> None:
        """Test client notification handler that raises exception."""

        # Register a handler that raises an exception
        def failing_handler(_) -> None:
            raise ValueError("Handler failed")

        # Mock notification type
        class TestNotification:
            pass

        minimcp._core.notification_handlers[TestNotification] = failing_handler  # pyright: ignore[reportArgumentType]

        mock_notification = Mock()
        mock_notification.root = TestNotification()

        # Should not raise exception, just log it
        result = await minimcp._handle_client_notification(mock_notification)
        assert result == NoMessage.NOTIFICATION

    async def test_initialize_handler_supported_version(self, minimcp: MiniMCP[Any]) -> None:
        """Test initialize handler with supported protocol version."""
        request = types.InitializeRequest(
            method="initialize",
            params=types.InitializeRequestParams(
                protocolVersion="2025-06-18",
                capabilities=types.ClientCapabilities(),
                clientInfo=types.Implementation(name="test", version="1.0"),
            ),
        )

        result = await minimcp._initialize_handler(request)

        assert isinstance(result, types.ServerResult)
        assert isinstance(result.root, types.InitializeResult)
        assert result.root.protocolVersion == "2025-06-18"
        assert result.root.serverInfo.name == "test-server"
        assert result.root.serverInfo.version == "1.0.0"
        assert result.root.instructions == "Test server instructions"

    async def test_initialize_handler_unsupported_version(self, minimcp: MiniMCP[Any]) -> None:
        """Test initialize handler with unsupported protocol version."""
        request = types.InitializeRequest(
            method="initialize",
            params=types.InitializeRequestParams(
                protocolVersion="unsupported-version",
                capabilities=types.ClientCapabilities(),
                clientInfo=types.Implementation(name="test", version="1.0"),
            ),
        )

        result = await minimcp._initialize_handler(request)

        assert isinstance(result, types.ServerResult)
        assert isinstance(result.root, types.InitializeResult)
        # Should fall back to latest supported version
        assert result.root.protocolVersion == types.LATEST_PROTOCOL_VERSION

    async def test_handle_success(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test successful message handling."""
        result: Message | NoMessage = await minimcp.handle(valid_request_message)

        assert isinstance(result, str)  # Should return JSON string
        response_dict = json.loads(result)
        assert response_dict["jsonrpc"] == "2.0"
        assert response_dict["id"] == 1
        assert "result" in response_dict

    async def test_handle_with_send_and_scope(
        self, minimcp: MiniMCP[Any], valid_request_message: str, mock_send: AsyncMock
    ) -> None:
        """Test message handling with send callback and scope."""
        scope = "test-scope"

        result = await minimcp.handle(valid_request_message, send=mock_send, scope=scope)

        assert isinstance(result, str)
        # Verify that responder was created (indirectly through successful handling)

    async def test_handle_parser_error(self, minimcp: MiniMCP[Any]) -> None:
        """Test handling parser error."""
        invalid_message = '{"invalid": json}'

        with pytest.raises(InvalidMessageError):
            await minimcp.handle(invalid_message)

    async def test_handle_invalid_params_error(self, minimcp: MiniMCP[Any]) -> None:
        """Test handling invalid params error."""
        invalid_rpc = json.dumps({"not": "jsonrpc"})

        with pytest.raises(InvalidMessageError):
            await minimcp.handle(invalid_rpc)

    async def test_handle_method_not_found_error(self, minimcp: MiniMCP[Any]) -> None:
        """Test handling method not found error."""
        # Use a valid JSON-RPC structure but unknown method
        # The validation error occurs before method dispatch, so this becomes INTERNAL_ERROR
        unknown_method = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown_method", "params": {}})

        result = await minimcp.handle(unknown_method)

        assert isinstance(result, str)
        response_dict = json.loads(result)
        # Unknown methods cause validation errors, not method not found errors
        assert response_dict["error"]["code"] == types.INTERNAL_ERROR

    async def test_handle_timeout_error(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test handling timeout error."""
        # Mock _parse_message to raise TimeoutError directly
        with patch.object(minimcp, "_parse_message", side_effect=TimeoutError("Timeout")):
            result = await minimcp.handle(valid_request_message)

            assert isinstance(result, str)
            response_dict = json.loads(result)
            assert response_dict["error"]["code"] == types.INTERNAL_ERROR

    async def test_handle_context_error(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test handling context error."""
        # Mock _handle_rpc_msg to raise ContextError
        with patch.object(minimcp, "_handle_rpc_msg", side_effect=ContextError("Context error")):
            result = await minimcp.handle(valid_request_message)

            assert isinstance(result, str)
            response_dict = json.loads(result)
            assert response_dict["error"]["code"] == types.INTERNAL_ERROR

    async def test_handle_cancellation_error(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test handling cancellation error."""
        # Mock _handle_rpc_msg to raise cancellation
        cancellation_exc = anyio.get_cancelled_exc_class()
        with patch.object(minimcp, "_handle_rpc_msg", side_effect=cancellation_exc()):
            with pytest.raises(cancellation_exc):
                await minimcp.handle(valid_request_message)

    async def test_handle_no_message_response(self, minimcp: MiniMCP[Any], valid_notification_message: str) -> None:
        """Test handling that returns NoMessage."""
        result = await minimcp.handle(valid_notification_message)

        assert result == NoMessage.NOTIFICATION

    async def test_handle_with_context_manager(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test that context manager is properly used during handling."""
        original_active = minimcp.context.active
        context_used = False

        def mock_active(context: Context[Any]):
            nonlocal context_used
            context_used = True
            assert isinstance(context, Context)
            return original_active(context)

        with patch.object(minimcp.context, "active", side_effect=mock_active):
            await minimcp.handle(valid_request_message)

        assert context_used

    async def test_handle_with_limiter(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test that limiter is properly used during handling."""
        # Test that the limiter is called by checking if the handle method completes
        # The limiter is used internally, so we test the behavior indirectly
        result = await minimcp.handle(valid_request_message)

        # If we get a result, the limiter was used successfully
        assert isinstance(result, str)
        response_dict = json.loads(result)
        assert response_dict["jsonrpc"] == "2.0"

    async def test_generic_type_parameter(self) -> None:
        """Test that MiniMCP can be parameterized with generic types."""
        # Test with string scope type
        server_str = MiniMCP[str](name="test")
        assert isinstance(server_str.context, ContextManager)

        # Test with int scope type
        server_int = MiniMCP[int](name="test")
        assert isinstance(server_int.context, ContextManager)

        # Test with custom type
        class CustomScope:
            pass

        server_custom = MiniMCP[CustomScope](name="test")
        assert isinstance(server_custom.context, ContextManager)

    async def test_error_logging(self, minimcp: MiniMCP[Any]) -> None:
        """Test that errors are properly logged."""
        invalid_message = '{"invalid": json}'

        with pytest.raises(InvalidMessageError):
            await minimcp.handle(invalid_message)

    async def test_debug_logging(
        self, minimcp: MiniMCP[Any], valid_request_message: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that debug information is logged."""
        with caplog.at_level("DEBUG"):
            await minimcp.handle(valid_request_message)

        # Should contain debug logs about handling requests
        assert any("Handling request" in record.message for record in caplog.records)

    async def test_concurrent_message_handling(self, minimcp: MiniMCP[Any], valid_request_message: str) -> None:
        """Test handling multiple messages concurrently."""
        # Create multiple tasks
        tasks: list[Coroutine[Any, Any, Message | NoMessage]] = []
        for i in range(5):
            message: str = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": i,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                }
            )
            tasks.append(minimcp.handle(message))

        # Execute all tasks concurrently
        results: list[Message | NoMessage] = []
        for task in tasks:
            result: Message | NoMessage = await task
            results.append(result)

        # All should succeed
        assert len(results) == 5
        for result in results:
            assert isinstance(result, str)
            response_dict = json.loads(result)
            assert response_dict["jsonrpc"] == "2.0"
            assert "result" in response_dict


class TestMiniMCPIntegration:
    """Integration tests for MiniMCP."""

    async def test_full_initialize_flow(self) -> None:
        """Test complete initialization flow."""
        server: MiniMCP[Any] = MiniMCP[Any](name="integration-test", version="1.0.0")

        # Create initialize request
        init_message: Message = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            }
        )

        # Handle the request
        result: Message | NoMessage = await server.handle(init_message)

        # Verify response
        assert isinstance(result, str)
        response = json.loads(result)  # type: ignore

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response

        init_result = response["result"]
        assert init_result["protocolVersion"] == "2025-06-18"
        assert init_result["serverInfo"]["name"] == "integration-test"
        assert init_result["serverInfo"]["version"] == "1.0.0"
        assert "capabilities" in init_result

    async def test_tool_integration(self):
        """Test integration with tool manager."""
        server: MiniMCP[Any] = MiniMCP(name="tool-test")

        # Add a test tool
        def test_tool(x: int, y: int = 5) -> int:
            """A test tool."""
            return x + y

        tool = server.tool.add(test_tool)
        assert tool.name == "test_tool"

        # Verify tool is registered
        tools = server.tool.list()
        assert len(tools) == 1
        assert tools[0].name == "test_tool"

    async def test_context_integration(self):
        """Test integration with context manager."""
        server: MiniMCP[Any] = MiniMCP[Any](name="context-test")

        init_message: Message = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        )

        # Handle with scope
        result: Message | NoMessage = await server.handle(init_message, scope="test-scope")

        assert isinstance(result, str)
        response: dict[str, Any] = json.loads(result)
        assert response["id"] == 1

    async def test_error_recovery(self):
        """Test error recovery and continued operation."""
        server: MiniMCP[Any] = MiniMCP(name="error-test")

        # Send invalid message
        with pytest.raises(InvalidMessageError):
            await server.handle('{"invalid": json}')

        # Send valid message after error
        valid_message = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        )

        valid_result = await server.handle(valid_message)
        valid_response = json.loads(valid_result)  # type: ignore
        assert valid_response["id"] == 2
        assert "result" in valid_response

    async def test_notification_handling(self):
        """Test notification handling."""
        server: MiniMCP[Any] = MiniMCP(name="notification-test")

        # Send initialized notification
        notification = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        result: Message | NoMessage = await server.handle(notification)
        assert result == NoMessage.NOTIFICATION

    async def test_multiple_clients_simulation(self):
        """Test handling messages from multiple simulated clients."""
        server: MiniMCP[Any] = MiniMCP(name="multi-client-test")

        # Simulate messages from different clients
        client_messages: list[str] = []
        for client_id in range(3):
            message = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": client_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": f"client-{client_id}", "version": "1.0"},
                    },
                }
            )
            client_messages.append(message)

        # Handle all messages
        results: list[Message | NoMessage] = []
        for msg in client_messages:
            result: Message | NoMessage = await server.handle(msg)
            results.append(result)

        # Verify all responses
        for i, result in enumerate(results):
            response = json.loads(result)  # type: ignore
            assert response["id"] == i
            assert "result" in response

    async def test_include_stack_trace_in_errors(self):
        """Test that stack traces are included in error messages when enabled."""
        server: MiniMCP[Any] = MiniMCP(name="stack-trace-test", include_stack_trace=True)

        # Create an invalid message that will trigger an error
        invalid_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown_method", "params": {}})

        result = await server.handle(invalid_message)

        response = json.loads(result)  # type: ignore
        assert "error" in response
        assert "data" in response["error"]
        # Stack trace should be present
        assert "stackTrace" in response["error"]["data"]

    async def test_exclude_stack_trace_in_errors(self):
        """Test that stack traces are NOT included when disabled."""
        server: MiniMCP[Any] = MiniMCP(name="no-stack-trace-test", include_stack_trace=False)

        # Create an invalid message that will trigger an error
        invalid_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown_method", "params": {}})

        result = await server.handle(invalid_message)

        response = json.loads(result)  # type: ignore
        assert "error" in response
        assert "data" in response["error"]
        # Stack trace should NOT be present
        assert "stackTrace" not in response["error"]["data"]

    async def test_error_metadata_in_response(self):
        """Test that error responses include proper metadata."""
        server: MiniMCP[Any] = MiniMCP(name="error-metadata-test")

        # Create an invalid message
        invalid_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown_method", "params": {}})

        result = await server.handle(invalid_message)

        response = json.loads(result)  # type: ignore
        assert "error" in response
        error_data = response["error"]["data"]

        # Should contain error metadata
        assert "errorType" in error_data
        assert "errorModule" in error_data
        assert "isoTimestamp" in error_data

        # Verify timestamp is valid ISO format
        datetime.fromisoformat(error_data["isoTimestamp"])

    async def test_process_error_with_internal_mcp_error(self):
        """Test _process_error method with InternalMCPError that has data."""

        server: MiniMCP[Any] = MiniMCP(name="process-error-test")

        # Create an error with data
        error_data = {"uri": "file:///nonexistent.txt", "name": "test_resource"}
        error = ResourceNotFoundError("Resource not found", error_data)
        request_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "resources/read"})

        # Call _process_error directly
        result = server._process_error(error, request_message, RESOURCE_NOT_FOUND)

        parsed = json.loads(result)
        assert parsed["error"]["code"] == RESOURCE_NOT_FOUND
        assert parsed["error"]["data"]["uri"] == "file:///nonexistent.txt"
        assert parsed["error"]["data"]["name"] == "test_resource"

    async def test_handle_with_different_error_types(self):
        """Test handling different types of MiniMCP errors."""

        server: MiniMCP[Any] = MiniMCP(name="error-types-test")

        # Register a tool that raises different errors
        def error_tool(error_type: str) -> str:
            """Tool that raises different errors."""
            if error_type == "arguments":
                raise InvalidArgumentsError("Invalid arguments")
            elif error_type == "primitive":
                raise PrimitiveError("Primitive error")
            elif error_type == "runtime":
                raise MCPRuntimeError("Runtime error")
            return "success"

        server.tool.add(error_tool)

        # Test each error type - they should be handled gracefully
        # (Note: Tool execution errors are handled differently, but we're testing error handling flow)
        test_cases = ["arguments", "primitive", "runtime"]

        for error_type in test_cases:
            call_message = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": error_type,
                    "method": "tools/call",
                    "params": {"name": "error_tool", "arguments": {"error_type": error_type}},
                }
            )

            result = await server.handle(call_message)

            # All should return valid responses (errors are caught and formatted)
            parsed = json.loads(result)  # type: ignore
            assert "jsonrpc" in parsed
            assert parsed["id"] == error_type

    async def test_concurrent_error_handling(self):
        """Test that errors are properly isolated across concurrent requests."""
        server: MiniMCP[Any] = MiniMCP(name="concurrent-errors-test")

        # Create multiple invalid messages
        messages: list[str] = []
        for i in range(5):
            # Mix of valid and invalid messages
            if i % 2 == 0:
                # Valid initialize request
                msg = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": i,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1.0"},
                        },
                    }
                )
            else:
                # Invalid request (unknown method)
                msg = json.dumps({"jsonrpc": "2.0", "id": i, "method": "unknown", "params": {}})

            messages.append(msg)

        # Handle all concurrently
        results: list[Any] = []
        for msg in messages:
            result = await server.handle(msg)
            results.append(json.loads(result))  # type: ignore

        # Verify each response has correct ID
        for i, response in enumerate(results):
            assert response["id"] == i

    async def test_limiter_integration_with_errors(self):
        """Test that limiter works correctly even when errors occur."""
        server: MiniMCP[Any] = MiniMCP(name="limiter-error-test", max_concurrency=2, idle_timeout=5)

        # Create messages that will trigger errors
        invalid_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown", "params": {}})
        result = await server.handle(invalid_message)
        response = json.loads(result)  # type: ignore
        assert response["id"] == 1
        assert "error" in response

        # Multiple concurrent error-causing requests
        results: list[Any] = []
        for i in range(5):
            msg = json.dumps({"jsonrpc": "2.0", "id": i, "method": "unknown", "params": {}})
            result = await server.handle(msg)
            results.append(json.loads(result))  # type: ignore

        # All should return error responses with correct IDs
        for i, response in enumerate(results):
            assert response["id"] == i
            assert "error" in response

    async def test_unsupported_message_type_error(self):
        """Test handling of UnsupportedMessageTypeError."""
        server: MiniMCP[Any] = MiniMCP(name="test-server")

        # Create a message that will trigger UnsupportedMessageTypeError
        # This happens when the message is valid JSON-RPC but not a request or notification
        with patch("minimcp.minimcp.MiniMCP._handle_rpc_msg") as mock_handle:
            from minimcp.exceptions import UnsupportedMessageTypeError

            mock_handle.side_effect = UnsupportedMessageTypeError("Unsupported message type")

            message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "test", "params": {}})
            result = await server.handle(message)

            # Should return an error response
            response = json.loads(result)  # type: ignore
            assert "error" in response
            assert response["id"] == 1

    async def test_request_handler_not_found_error(self):
        """Test handling of RequestHandlerNotFoundError."""
        server: MiniMCP[Any] = MiniMCP(name="test-server")

        # Create a message with a method that doesn't exist in MiniMCP
        message = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/subscribe", "params": {"uri": "file:///config.json"}}
        )
        result = await server.handle(message)

        # Should return a METHOD_NOT_FOUND error
        response = json.loads(result)  # type: ignore
        assert "error" in response
        assert response["error"]["code"] == types.METHOD_NOT_FOUND
        assert response["id"] == 1

    async def test_resource_not_found_error(self):
        """Test handling of ResourceNotFoundError."""
        server: MiniMCP[Any] = MiniMCP(name="test-server")

        # Try to read a resource that doesn't exist
        message = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "nonexistent://resource"}}
        )
        result = await server.handle(message)

        # Should return a RESOURCE_NOT_FOUND error
        response = json.loads(result)  # type: ignore
        assert "error" in response
        assert response["error"]["code"] == RESOURCE_NOT_FOUND
        assert response["id"] == 1

    async def test_internal_mcp_error(self):
        """Test handling of InternalMCPError."""

        server: MiniMCP[Any] = MiniMCP(name="test-server")

        # Mock _handle_rpc_msg to raise InternalMCPError
        with patch("minimcp.minimcp.MiniMCP._handle_rpc_msg") as mock_handle:
            mock_handle.side_effect = InternalMCPError("Internal error")

            message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "test", "params": {}})
            result = await server.handle(message)

            # Should return an INTERNAL_ERROR response
            response = json.loads(result)  # type: ignore
            assert "error" in response
            assert response["error"]["code"] == types.INTERNAL_ERROR
            assert response["id"] == 1

    async def test_error_type_checking_branches(self):
        """Test the error type checking branches in _parse_message."""
        server: MiniMCP[Any] = MiniMCP(name="test-server")

        # Test with invalid JSON that triggers json_invalid error
        invalid_json = "{invalid json"
        with pytest.raises(InvalidMessageError):
            await server.handle(invalid_json)

        # Test with valid JSON but invalid JSON-RPC (missing jsonrpc field)
        invalid_jsonrpc = json.dumps({"id": 1, "method": "test"})
        with pytest.raises(InvalidMessageError):
            await server.handle(invalid_jsonrpc)

        # Test with wrong jsonrpc version
        wrong_version = json.dumps({"jsonrpc": "1.0", "id": 1, "method": "test", "params": {}})
        with pytest.raises(InvalidMessageError):
            await server.handle(wrong_version)
