"""
Integration tests for MCP server using official MCP stdio client.
"""

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import anyio
import pytest
from helpers.client_session_with_init import ClientSessionWithInit
from mcp import McpError, StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent, TextResourceContents
from pydantic import AnyUrl

pytestmark = pytest.mark.anyio


class TestStdioServer:
    """Test suite for stdio server."""

    @pytest.fixture(autouse=True)
    async def timeout_5s(self):
        """Fail test if it takes longer than 5 seconds."""
        with anyio.fail_after(5):
            yield

    @pytest.fixture(scope="class")
    async def mcp_client(self) -> AsyncGenerator[ClientSessionWithInit, None]:
        """Create and manage an MCP client connected to our test server."""
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", "tests.integration.servers.stdio_server"],
            env={
                "UV_INDEX": os.environ.get("UV_INDEX", ""),
                "PYTHONPATH": str(Path(__file__).parent.parent.parent.parent),
            },
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSessionWithInit(read, write) as session:
                session.initialize_result = await session.initialize()
                yield session

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

        # Resource not found is a protocol error, so it should raise a McpError
        # https://modelcontextprotocol.io/specification/2025-06-18/server/resources#error-handling
        with pytest.raises(McpError):
            await mcp_client.read_resource(AnyUrl("math://nonexistent"))

    async def test_tool_call_with_invalid_parameters(self, mcp_client: ClientSessionWithInit):
        """Test calling a tool with invalid parameters."""

        # Invalid parameters is a protocol error, so it should raise a McpError
        # https://modelcontextprotocol.io/specification/2025-06-18/server/tools#error-handling
        with pytest.raises(McpError):
            await mcp_client.call_tool("add", {"a": 5.0})  # Missing 'b' parameter

    async def test_add_with_progress_tool(self, mcp_client: ClientSessionWithInit):
        """Test calling the add_with_progress tool which sends progress notifications."""
        # Test that the tool exists and can be called
        tools = (await mcp_client.list_tools()).tools
        tool_names = [tool.name for tool in tools]
        assert "add_with_progress" in tool_names, f"add_with_progress tool not found in {tool_names}"

        # Call the tool with progress reporting
        result = await mcp_client.call_tool("add_with_progress", {"a": 5.0, "b": 3.0})

        # Verify the result
        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 8.0

    async def test_add_with_progress_tool_with_progress_handler(self, mcp_client: ClientSessionWithInit):
        """Test calling the add_with_progress tool with a progress handler to capture progress notifications."""

        # Track progress notifications
        progress_notifications: list[dict[str, float | str | None]] = []

        async def progress_handler(progress: float, total: float | None, message: str | None) -> None:
            """Capture progress notifications."""
            progress_notifications.append({"progress": progress, "total": total, "message": message})

        # Test that the tool exists and can be called
        tools = (await mcp_client.list_tools()).tools
        tool_names = [tool.name for tool in tools]
        assert "add_with_progress" in tool_names, f"add_with_progress tool not found in {tool_names}"

        # Call the tool with progress reporting
        result = await mcp_client.call_tool(
            "add_with_progress", {"a": 7.0, "b": 13.0}, progress_callback=progress_handler
        )

        # Verify the result
        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 20.0

        # Verify progress notifications were received
        assert len(progress_notifications) > 0, "No progress notifications were received"

        # Verify we got the expected progress values (0.1, 0.4, 0.7 from the implementation)
        progress_values = [n["progress"] for n in progress_notifications]
        expected_progress = [0.1, 0.4, 0.7]
        assert progress_values == expected_progress, f"Expected progress {expected_progress}, got {progress_values}"

    async def test_async_tool_execution(self, mcp_client: ClientSessionWithInit):
        """Test that async tools (with MCPFunc) execute correctly with stdio transport."""
        # Call the async tool with progress reporting
        # Stdio supports progress notifications
        result = await mcp_client.call_tool("add_with_progress", {"a": 15.0, "b": 25.0})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 40.0

    async def test_progress_tool_with_type_coercion(self, mcp_client: ClientSessionWithInit):
        """Test type coercion (string to float) works with progress-enabled async tools."""
        # MCPFunc should coerce string arguments to float for the tool
        result = await mcp_client.call_tool("add_with_progress", {"a": "5.5", "b": "3.2"})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert abs(float(result.content[0].text) - 8.7) < 0.0001  # Allow for floating point precision

    async def test_progress_tool_error_wrapping(self, mcp_client: ClientSessionWithInit):
        """Test that errors in async tools with progress are wrapped in MCPRuntimeError."""
        # The divide tool should raise ValueError for division by zero
        result = await mcp_client.call_tool("divide", {"a": 10.0, "b": 0.0})

        assert result.isError is True
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        # Verify error message contains information about the wrapped exception
        error_text = result.content[0].text.lower()
        assert "cannot divide by zero" in error_text or "division by zero" in error_text

    async def test_concurrent_progress_tools(self, mcp_client: ClientSessionWithInit):
        """Test multiple async tools with progress reporting executing concurrently."""
        # Store results keyed by call_id
        results: dict[str, CallToolResult] = {}

        async def make_call(call_id: str, a: float, b: float) -> None:
            result = await mcp_client.call_tool("add_with_progress", {"a": a, "b": b})
            results[call_id] = result

        # Execute multiple calls concurrently
        async with anyio.create_task_group() as tg:
            tg.start_soon(make_call, "call1", 1.0, 2.0)
            tg.start_soon(make_call, "call2", 3.0, 4.0)
            tg.start_soon(make_call, "call3", 5.0, 6.0)

        # Verify all results are correct
        expected_results = {"call1": 3.0, "call2": 7.0, "call3": 11.0}
        for call_id, expected_value in expected_results.items():
            assert results[call_id].isError is False
            assert len(results[call_id].content) == 1
            assert results[call_id].content[0].type == "text"
            assert isinstance(results[call_id].content[0], TextContent)
            assert float(results[call_id].content[0].text) == expected_value  # type: ignore[union-attr]

    async def test_progress_tool_with_invalid_parameters(self, mcp_client: ClientSessionWithInit):
        """Test that parameter validation errors are reported correctly for async progress tools."""
        # Pass invalid parameter type that cannot be coerced
        with pytest.raises(McpError):
            await mcp_client.call_tool("add_with_progress", {"a": "not_a_number", "b": 5.0})

    async def test_progress_handler_exception_handling(self, mcp_client: ClientSessionWithInit):
        """Test that exceptions in progress handlers don't break tool execution."""

        async def failing_progress_handler(progress: float, total: float | None, message: str | None) -> None:
            """Progress handler that throws an exception after first progress update."""
            if progress > 0.2:
                raise Exception("Progress handler error")

        # Should still complete successfully despite handler errors
        result = await mcp_client.call_tool(
            "add_with_progress", {"a": 10.0, "b": 20.0}, progress_callback=failing_progress_handler
        )

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 30.0

    async def test_async_prompt_execution(self, mcp_client: ClientSessionWithInit):
        """Test that prompts execute correctly through stdio transport."""
        # Get a prompt from the server
        result = await mcp_client.get_prompt("math_help", {"operation": "division"})

        # Verify the prompt was returned correctly
        assert result is not None
        assert len(result.messages) > 0
        # Check that the operation is mentioned in the prompt content
        # Ensure content is TextContent before accessing .text
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        prompt_text = content.text.lower()
        assert "division" in prompt_text
        assert "mathematical" in prompt_text or "math" in prompt_text

    # ====== MCPFunc Type Coercion and Validation Tests ======

    async def test_tool_with_string_number_coercion(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc coerces string numbers to numeric types."""
        # Pass string arguments that should be coerced to float
        result = await mcp_client.call_tool("add", {"a": "10.5", "b": "5.5"})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 16.0

    async def test_tool_with_invalid_type_coercion(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc properly rejects invalid type coercions."""
        # Pass a string that cannot be coerced to a number
        with pytest.raises(McpError):
            await mcp_client.call_tool("add", {"a": "not_a_number", "b": 5.0})

    async def test_tool_with_integer_inputs(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc accepts integer inputs for float parameters."""
        # Pass integer arguments for float parameters
        result = await mcp_client.call_tool("multiply", {"a": 7, "b": 6})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 42.0

    async def test_tool_with_mixed_numeric_types(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc handles mixed integer and float inputs correctly."""
        # Pass a mix of int and float arguments
        result = await mcp_client.call_tool("subtract", {"a": 20, "b": 7.5})

        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert float(result.content[0].text) == 12.5

    # ====== MCPFunc Schema and Parameter Tests ======

    async def test_tool_parameter_descriptions_in_schema(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc extracts parameter descriptions from Field annotations."""
        tools = (await mcp_client.list_tools()).tools
        add_tool = next(tool for tool in tools if tool.name == "add")

        # Check that parameter descriptions from Field(description=...) are in the schema
        assert "a" in add_tool.inputSchema["properties"]
        assert "description" in add_tool.inputSchema["properties"]["a"]
        assert "first number" in add_tool.inputSchema["properties"]["a"]["description"].lower()

        assert "b" in add_tool.inputSchema["properties"]
        assert "description" in add_tool.inputSchema["properties"]["b"]
        assert "second number" in add_tool.inputSchema["properties"]["b"]["description"].lower()

    async def test_tool_required_vs_optional_parameters(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc correctly identifies required vs optional parameters."""
        tools = (await mcp_client.list_tools()).tools
        add_tool = next(tool for tool in tools if tool.name == "add")

        # Both a and b should be required for the add tool
        assert "required" in add_tool.inputSchema
        assert "a" in add_tool.inputSchema["required"]
        assert "b" in add_tool.inputSchema["required"]

    async def test_tool_schema_reflects_mcp_func_validation(self, mcp_client: ClientSessionWithInit):
        """Test that tool schemas reflect MCPFunc's validation rules."""
        tools = (await mcp_client.list_tools()).tools
        multiply_tool = next(tool for tool in tools if tool.name == "multiply")

        # Check that the schema includes type information
        assert multiply_tool.inputSchema["properties"]["a"]["type"] == "number"
        assert multiply_tool.inputSchema["properties"]["b"]["type"] == "number"

    # ====== MCPFunc Prompt Validation Tests ======

    async def test_prompt_parameter_validation(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc validates prompt parameters correctly."""
        # Get a prompt with valid parameters
        result = await mcp_client.get_prompt("math_help", {"operation": "multiplication"})

        assert result is not None
        assert len(result.messages) > 0
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "multiplication" in content.text.lower()

    async def test_prompt_missing_required_parameter(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc rejects prompts with missing required parameters."""
        # Try to get a prompt without required parameter
        with pytest.raises(Exception) as exc_info:
            await mcp_client.get_prompt("math_help", {})

        # Should get an error about missing parameter
        error_message = str(exc_info.value).lower()
        assert "field required" in error_message or "required" in error_message or "operation" in error_message

    # ====== MCPFunc Resource Template Tests ======

    async def test_resource_template_parameter_validation(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc validates resource template parameters correctly."""
        # Read a resource template with valid parameters
        result = (await mcp_client.read_resource(AnyUrl("math://constants/e"))).contents

        assert len(result) == 1
        assert isinstance(result[0], TextResourceContents)
        content_text = result[0].text
        assert "2.71828" in content_text

    async def test_resource_template_with_invalid_parameter(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc handles invalid resource template parameters."""
        # Try to read a resource with an invalid parameter value
        from mcp.shared.exceptions import McpError

        with pytest.raises(McpError, match="Unknown constant: nonexistent"):
            await mcp_client.read_resource(AnyUrl("math://constants/nonexistent"))

    # ====== MCPFunc Error Handling Tests ======

    async def test_tool_exception_wrapping(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc wraps tool exceptions in MCPRuntimeError."""
        # Call divide with zero to trigger exception
        result = await mcp_client.call_tool("divide", {"a": 100.0, "b": 0.0})

        assert result.isError is True
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        # Verify the error message contains the original exception info
        error_text = result.content[0].text
        assert "Cannot divide by zero" in error_text

    # ====== MCPFunc Concurrency Tests ======

    async def test_concurrent_tool_calls_with_validation(self, mcp_client: ClientSessionWithInit):
        """Test that MCPFunc handles concurrent tool calls with validation correctly."""

        # Execute multiple different tools concurrently
        results: dict[int, CallToolResult] = {}

        async def execute_call(index: int, name: str, args: dict[str, Any]) -> None:
            results[index] = await mcp_client.call_tool(name, args)

        async with anyio.create_task_group() as tg:
            tg.start_soon(execute_call, 0, "add", {"a": "10.5", "b": "5.5"})  # Type coercion
            tg.start_soon(execute_call, 1, "multiply", {"a": 3, "b": 4})  # Integer to float
            tg.start_soon(execute_call, 2, "subtract", {"a": 20.0, "b": 7.5})  # Mixed types

        # Type guard: Verify all results were populated
        assert len(results) == 3

        # Verify all results
        assert results[0].isError is False
        assert results[1].isError is False
        assert results[2].isError is False

        assert results[0].structuredContent is not None
        assert results[1].structuredContent is not None
        assert results[2].structuredContent is not None
        assert float(results[0].structuredContent["result"]) == 16.0
        assert float(results[1].structuredContent["result"]) == 12.0
        assert float(results[2].structuredContent["result"]) == 12.5
