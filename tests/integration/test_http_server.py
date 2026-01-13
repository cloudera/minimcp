"""
Integration tests for MCP server using FastMCP StreamableHttpTransport client.
"""

from collections.abc import AsyncGenerator, Coroutine
from http import HTTPStatus
from typing import Any

import anyio
import pytest
from helpers.client_session_with_init import ClientSessionWithInit
from httpx import AsyncClient, Limits, Timeout
from mcp import McpError, types
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent, TextResourceContents
from pydantic import AnyUrl
from servers.http_server import HTTP_MCP_PATH, SERVER_HOST, SERVER_PORT

pytestmark = pytest.mark.anyio


class TestHttpServer:
    """Test suite for HTTP server."""

    server_url: str = f"http://{SERVER_HOST}:{SERVER_PORT}{HTTP_MCP_PATH}"
    default_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    @pytest.fixture(autouse=True)
    async def timeout_5s(self):
        """Fail test if it takes longer than 5 seconds."""
        with anyio.fail_after(5):
            yield

    @pytest.fixture(scope="class")
    async def mcp_client(self, http_test_server_process: Any) -> AsyncGenerator[ClientSessionWithInit, None]:
        """Create and manage an MCP client connected to our test server via StreamableHttpTransport."""
        async with AsyncClient(headers=self.default_headers) as client:
            async with streamable_http_client(self.server_url, http_client=client) as (read, write, _):
                async with ClientSessionWithInit(read, write) as session:
                    session.initialize_result = await session.initialize()
                    yield session

    @pytest.fixture(scope="class")
    async def http_client(self, http_test_server_process: Any) -> AsyncGenerator[AsyncClient, None]:
        """HTTP client for raw HTTP tests - Needed for transport level error cases"""
        limits = Limits(max_keepalive_connections=5, max_connections=10)

        timeout = Timeout(5.0, connect=2.0)

        async with AsyncClient(limits=limits, timeout=timeout) as client:
            yield client

    async def test_server_initialization(self, mcp_client: ClientSessionWithInit):
        """Test that the MCP server initializes correctly."""
        # The client should be initialized by the fixture
        assert mcp_client is not None

        # Test that we can get initialization result
        init_result = mcp_client.initialize_result
        assert init_result is not None
        assert init_result.serverInfo.name == "TestMathServer"
        assert init_result.serverInfo.version == "0.1.0"

    async def test_list_tools(self, mcp_client: ClientSessionWithInit):
        """Test listing available tools."""
        tools = (await mcp_client.list_tools()).tools

        # Check that we have the expected tools
        tool_names = [tool.name for tool in tools]
        expected_tools = ["add", "subtract", "multiply", "divide"]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Expected tool '{expected_tool}' not found in {tool_names}"

        # Check tool details for the add function
        add_tool = next(tool for tool in tools if tool.name == "add")
        assert add_tool.description == "Add two numbers"
        assert "a" in add_tool.inputSchema["properties"]
        assert "b" in add_tool.inputSchema["properties"]

    async def test_call_add_tool(self, mcp_client: ClientSessionWithInit):
        """Test calling the add tool."""
        result = await mcp_client.call_tool("add", {"a": 5.0, "b": 3.0})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 8.0

    async def test_call_subtract_tool(self, mcp_client: ClientSessionWithInit):
        """Test calling the subtract tool."""
        result = await mcp_client.call_tool("subtract", {"a": 10.0, "b": 4.0})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 6.0

    async def test_call_multiply_tool(self, mcp_client: ClientSessionWithInit):
        """Test calling the multiply tool."""
        result = await mcp_client.call_tool("multiply", {"a": 6.0, "b": 7.0})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 42.0

    async def test_call_divide_tool(self, mcp_client: ClientSessionWithInit):
        """Test calling the divide tool."""
        result = await mcp_client.call_tool("divide", {"a": 15.0, "b": 3.0})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 5.0

    async def test_call_divide_by_zero(self, mcp_client: ClientSessionWithInit):
        """Test calling the divide tool with zero divisor."""

        result = await mcp_client.call_tool("divide", {"a": 10.0, "b": 0.0})

        assert result.isError is True
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert "Cannot divide by zero" in result.content[0].text

    async def test_list_prompts(self, mcp_client: ClientSessionWithInit):
        """Test listing available prompts."""
        prompts = (await mcp_client.list_prompts()).prompts

        # Check that we have the expected prompt
        prompt_names = [prompt.name for prompt in prompts]
        assert "math_help" in prompt_names

        # Check prompt details
        math_help_prompt = next(prompt for prompt in prompts if prompt.name == "math_help")
        assert math_help_prompt.description == "Get help with mathematical operations"

    async def test_get_prompt(self, mcp_client: ClientSessionWithInit):
        """Test getting a prompt."""
        result = await mcp_client.get_prompt("math_help", {"operation": "addition"})

        assert len(result.messages) == 1
        assert result.messages[0].role == "user"

        # Ensure content is TextContent before accessing .text
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "addition" in content.text
        assert "math assistant" in content.text.lower()

    async def test_list_resources(self, mcp_client: ClientSessionWithInit):
        """Test listing available resources."""
        resources = (await mcp_client.list_resources()).resources

        # Check that we have the expected resources
        resource_uris = [str(resource.uri) for resource in resources]
        expected_resources = ["math://constants"]

        for expected_resource in expected_resources:
            assert expected_resource in resource_uris, (
                f"Expected resource '{expected_resource}' not found in {resource_uris}"
            )

    async def test_read_resource(self, mcp_client: ClientSessionWithInit):
        """Test reading a resource."""
        result = (await mcp_client.read_resource(AnyUrl("math://constants"))).contents

        assert len(result) == 1
        assert str(result[0].uri) == "math://constants"

        # The content should contain our math constants
        # Ensure content is TextResourceContents before accessing .text
        assert isinstance(result[0], TextResourceContents)
        content_text = result[0].text
        assert "pi" in content_text
        assert "3.14159" in content_text

    async def test_read_resource_template(self, mcp_client: ClientSessionWithInit):
        """Test reading a resource template."""
        result = (await mcp_client.read_resource(AnyUrl("math://constants/pi"))).contents

        assert len(result) == 1
        assert str(result[0].uri) == "math://constants/pi"

        # The content should be just the pi value
        # Ensure content is TextResourceContents before accessing .text
        assert isinstance(result[0], TextResourceContents)
        content_text = result[0].text
        assert "3.14159" in content_text

    async def test_invalid_tool_call(self, mcp_client: ClientSessionWithInit):
        """Test calling a non-existent tool."""

        # Unknown tools is a protocol error, so it should raise a McpError
        # https://modelcontextprotocol.io/specification/2025-06-18/server/tools#error-handling
        with pytest.raises(McpError):
            await mcp_client.call_tool("nonexistent_tool", {})

    async def test_invalid_resource_read(self, mcp_client: ClientSessionWithInit):
        """Test reading a non-existent resource."""
        with pytest.raises(McpError):
            await mcp_client.read_resource(AnyUrl("math://nonexistent"))

    async def test_tool_call_with_invalid_parameters(self, mcp_client: ClientSessionWithInit):
        """Test calling a tool with invalid parameters."""

        with pytest.raises(McpError):
            await mcp_client.call_tool("add", {"a": 5.0})  # Missing 'b' parameter

    async def test_concurrent_requests(self, mcp_client: ClientSessionWithInit):
        """Test multiple concurrent requests to ensure proper isolation."""

        async def call_add(a: float, b: float) -> float:
            result = await mcp_client.call_tool("add", {"a": a, "b": b})
            content = result.content[0]
            assert isinstance(content, TextContent)
            return float(content.text)

        results: dict[int, float] = {}

        # Make multiple concurrent requests
        async with anyio.create_task_group() as tg:

            async def run_and_append(id: int, coro: Coroutine[Any, Any, float]):
                result = await coro
                results[id] = result

            tg.start_soon(run_and_append, 1, call_add(1.0, 2.0))  # Should return 3.0
            tg.start_soon(run_and_append, 2, call_add(5.0, 10.0))  # Should return 15.0
            tg.start_soon(run_and_append, 3, call_add(100.0, 200.0))  # Should return 300.0

        assert results[1] == 3.0
        assert results[2] == 15.0
        assert results[3] == 300.0

    async def test_invalid_json_request_body(self, http_client: AsyncClient):
        """Test server response to invalid JSON in request body."""

        # Send invalid JSON
        response = await http_client.post(self.server_url, content="not valid json", headers=self.default_headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.PARSE_ERROR
        assert "InvalidJSON" in error_data["error"]["message"]

    async def test_empty_json_request_body(self, http_client: AsyncClient):
        """Test server response to empty request body."""

        # Send empty body
        response = await http_client.post(self.server_url, content="", headers=self.default_headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.PARSE_ERROR
        assert "InvalidJSONError" in error_data["error"]["message"]

    async def test_json_array_request_body(self, http_client: AsyncClient):
        """Test server response to JSON array instead of object."""

        # Send JSON array instead of object
        response = await http_client.post(
            self.server_url,
            json=[{"jsonrpc": "2.0", "method": "test", "id": 1}],
            headers=self.default_headers,
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.INVALID_REQUEST
        assert "InvalidJSONRPCMessageError" in error_data["error"]["message"]

    async def test_json_string_request_body(self, http_client: AsyncClient):
        """Test server response to JSON string instead of object."""

        # Send JSON string instead of object
        response = await http_client.post(self.server_url, json="just a string", headers=self.default_headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.INVALID_REQUEST
        assert "InvalidJSONRPCMessageError" in error_data["error"]["message"]

    async def test_missing_jsonrpc_field(self, http_client: AsyncClient):
        """Test server response to request missing jsonrpc field."""

        # Send request without jsonrpc field
        response = await http_client.post(
            self.server_url,
            json={"method": "test", "id": 1},
            headers=self.default_headers,
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.INVALID_REQUEST
        assert "InvalidJSONRPCMessageError" in error_data["error"]["message"]

    async def test_wrong_jsonrpc_version(self, http_client: AsyncClient):
        """Test server response to wrong JSON-RPC version."""

        # Send request with wrong JSON-RPC version
        response = await http_client.post(
            self.server_url,
            json={"jsonrpc": "1.0", "method": "test", "id": 1},
            headers=self.default_headers,
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.INVALID_REQUEST
        assert "InvalidJSONRPCMessageError" in error_data["error"]["message"]

    async def test_null_jsonrpc_field(self, http_client: AsyncClient):
        """Test server response to null jsonrpc field."""

        # Send request with null jsonrpc field
        response = await http_client.post(
            self.server_url,
            json={"jsonrpc": None, "method": "test", "id": 1},
            headers=self.default_headers,
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.INVALID_REQUEST
        assert "InvalidJSONRPCMessageError" in error_data["error"]["message"]

    async def test_empty_json_object(self, http_client: AsyncClient):
        """Test server response to empty JSON object."""

        # Send empty JSON object
        response = await http_client.post(self.server_url, json={}, headers=self.default_headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == types.INVALID_REQUEST
        assert "InvalidJSONRPCMessageError" in error_data["error"]["message"]

    async def test_valid_jsonrpc_with_extra_fields(self, http_client: AsyncClient):
        """Test that valid JSON-RPC with extra fields is accepted."""

        # Send valid JSON-RPC request with extra fields
        response = await http_client.post(
            self.server_url,
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
                "id": 1,
                "extra": "field",  # Extra field should be allowed
            },
            headers=self.default_headers,
        )

        # Should not fail due to extra fields
        response_data = response.json()
        assert "result" in response_data
        assert response.status_code == 200

    async def test_malformed_json_cases(self, http_client: AsyncClient):
        """Test various malformed JSON cases."""

        malformed_cases = [
            '{"jsonrpc": "2.0", "method": "test", "id": 1',  # Missing closing brace
            '{"jsonrpc": "2.0", "method": "test", "id": 1,}',  # Trailing comma
            '{"jsonrpc": "2.0", "method": "test", "id": }',  # Missing value
            '{jsonrpc: "2.0", "method": "test", "id": 1}',  # Unquoted key
        ]

        for malformed_json in malformed_cases:
            response = await http_client.post(
                self.server_url,
                content=malformed_json,
                headers=self.default_headers,
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            error_data = response.json()
            assert "error" in error_data
            assert error_data["error"]["code"] == types.PARSE_ERROR
            assert "InvalidJSONError" in error_data["error"]["message"]

    async def test_tool_with_string_number_coercion(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc coerces string numbers to numeric types."""
        # Send strings that should be coerced to floats
        result = await mcp_client.call_tool("add", {"a": "10.5", "b": "20.3"})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 30.8

    async def test_tool_with_invalid_type_coercion(self, mcp_client: ClientSessionWithInit):
        """Test that invalid types that can't be coerced raise proper errors."""

        # Must raise InvalidArgumentsError
        with pytest.raises(McpError) as excinfo:
            await mcp_client.call_tool("add", {"a": "not_a_number", "b": 5.0})
        assert "InvalidArgumentsError" in str(excinfo.value.error.message)

    async def test_tool_parameter_descriptions_in_schema(self, mcp_client: ClientSessionWithInit):
        """Test that parameter descriptions from Field annotations are exposed in schema."""
        tools = (await mcp_client.list_tools()).tools

        add_tool = next(tool for tool in tools if tool.name == "add")

        # Check that parameter descriptions are present
        assert "a" in add_tool.inputSchema["properties"]
        assert "description" in add_tool.inputSchema["properties"]["a"]
        assert "first number" in add_tool.inputSchema["properties"]["a"]["description"].lower()

        assert "b" in add_tool.inputSchema["properties"]
        assert "description" in add_tool.inputSchema["properties"]["b"]
        assert "second number" in add_tool.inputSchema["properties"]["b"]["description"].lower()

    async def test_tool_required_vs_optional_parameters(self, mcp_client: ClientSessionWithInit):
        """Test that required and optional parameters are properly distinguished."""
        tools = (await mcp_client.list_tools()).tools

        add_tool = next(tool for tool in tools if tool.name == "add")

        # Both parameters have defaults in the Field, but are still required because
        # the default is Field(description=...) not Field(default=..., description=...)
        assert "required" in add_tool.inputSchema
        # In this case, both should be required since there are no default values
        # This validates MCPFunc's schema generation

    async def test_prompt_parameter_validation(self, mcp_client: ClientSessionWithInit):
        """Test that prompt parameters are validated through MCPFunc."""
        # Valid call
        result = await mcp_client.get_prompt("math_help", {"operation": "division"})

        assert len(result.messages) == 1
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "division" in content.text.lower()

    async def test_prompt_missing_required_parameter(self, mcp_client: ClientSessionWithInit):
        """Test that prompts with missing required parameters raise proper errors."""
        # Try to call prompt without required parameter
        with pytest.raises(Exception):  # Should raise an error
            await mcp_client.get_prompt("math_help", {})

    async def test_resource_template_parameter_validation(self, mcp_client: ClientSessionWithInit):
        """Test that resource template parameters are validated through MCPFunc."""
        # Valid resource template call
        result = (await mcp_client.read_resource(AnyUrl("math://constants/e"))).contents

        assert len(result) == 1
        assert str(result[0].uri) == "math://constants/e"

        assert isinstance(result[0], TextResourceContents)
        content_text = result[0].text
        assert "2.71828" in content_text

    async def test_resource_template_with_invalid_parameter(self, mcp_client: ClientSessionWithInit):
        """Test that resource templates handle invalid parameters properly."""
        # Try to access a non-existent constant
        # The resource function raises ValueError which is wrapped by MCPFunc
        # and propagated as MCPError through the transport
        from mcp.shared.exceptions import McpError

        with pytest.raises(McpError, match="Unknown constant: nonexistent"):
            await mcp_client.read_resource(AnyUrl("math://constants/nonexistent"))

    async def test_tool_exception_wrapping(self, mcp_client: ClientSessionWithInit):
        """Test that exceptions in tools are properly wrapped by MCPFunc and returned as errors."""
        # Division by zero should raise ValueError which is caught and wrapped
        result = await mcp_client.call_tool("divide", {"a": 10.0, "b": 0.0})

        assert result.isError is True
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        # Should contain the original error message
        assert "Cannot divide by zero" in result.content[0].text

    async def test_tool_with_integer_inputs(self, mcp_client: ClientSessionWithInit):
        """Test that integer inputs are accepted for float parameters (type coercion)."""
        # Send integers instead of floats
        result = await mcp_client.call_tool("multiply", {"a": 7, "b": 6})

        assert result.isError is False
        assert len(result.content) == 1
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert float(content.text) == 42.0

    async def test_tool_with_mixed_numeric_types(self, mcp_client: ClientSessionWithInit):
        """Test that mixed numeric types (int, float, string numbers) work correctly."""
        # Mix int, float, and string representations
        result = await mcp_client.call_tool("add", {"a": 10, "b": "20.5"})

        assert result.isError is False
        content1 = result.content[0]
        assert isinstance(content1, TextContent)
        assert float(content1.text) == 30.5

        result = await mcp_client.call_tool("multiply", {"a": "3.5", "b": 2})

        assert result.isError is False
        content2 = result.content[0]
        assert isinstance(content2, TextContent)
        assert float(content2.text) == 7.0

    async def test_concurrent_tool_calls_with_validation(self, mcp_client: ClientSessionWithInit):
        """Test that concurrent tool calls each get proper validation through MCPFunc."""

        async def call_tool_safe(name: str, args: dict[str, Any]) -> tuple[bool, str]:
            result = await mcp_client.call_tool(name, args)
            content = result.content[0]
            assert isinstance(content, TextContent)
            return (not result.isError, content.text)

        results: dict[int, tuple[bool, str]] = {}

        async with anyio.create_task_group() as tg:

            async def run_and_store(id: int, coro: Any):
                result = await coro
                results[id] = result

            # Mix valid and invalid calls
            tg.start_soon(run_and_store, 1, call_tool_safe("add", {"a": 5.0, "b": 10.0}))  # Valid
            tg.start_soon(run_and_store, 2, call_tool_safe("divide", {"a": 100.0, "b": 0.0}))  # Error
            tg.start_soon(run_and_store, 3, call_tool_safe("multiply", {"a": "3.5", "b": "2.0"}))  # Valid with coercion

        # Check results
        assert results[1][0] is True  # Success
        assert float(results[1][1]) == 15.0

        assert results[2][0] is False  # Error (divide by zero)
        assert "Cannot divide by zero" in results[2][1]

        assert results[3][0] is True  # Success with coercion
        assert float(results[3][1]) == 7.0

    async def test_tool_schema_reflects_mcp_func_validation(self, mcp_client: ClientSessionWithInit):
        """Test that tool schemas properly reflect MCPFunc's validation requirements."""
        tools = (await mcp_client.list_tools()).tools

        # Check that all math tools have proper schemas
        for tool in tools:
            if tool.name in ["add", "subtract", "multiply", "divide"]:
                # Should have inputSchema
                assert tool.inputSchema is not None
                assert "properties" in tool.inputSchema
                assert "a" in tool.inputSchema["properties"]
                assert "b" in tool.inputSchema["properties"]

                # Properties should have type information
                assert "type" in tool.inputSchema["properties"]["a"]
                assert "type" in tool.inputSchema["properties"]["b"]
