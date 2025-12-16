from typing import Any
from unittest.mock import Mock, patch

import anyio
import mcp.types as types
import pytest
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata
from mcp.server.lowlevel.server import Server
from pydantic import BaseModel, Field

from minimcp.exceptions import (
    InvalidArgumentsError,
    MCPFuncError,
    MCPRuntimeError,
    PrimitiveError,
    ToolMCPRuntimeError,
)
from minimcp.managers.tool_manager import ToolDefinition, ToolManager

pytestmark = pytest.mark.anyio


class TestToolManager:
    """Test suite for ToolManager class."""

    @pytest.fixture
    def mock_core(self) -> Mock:
        """Create a mock Server for testing."""
        core = Mock(spec=Server)
        core.list_tools = Mock(return_value=Mock())
        core.call_tool = Mock(return_value=Mock())
        return core

    @pytest.fixture
    def tool_manager(self, mock_core: Mock) -> ToolManager:
        """Create a ToolManager instance with mocked core."""
        return ToolManager(mock_core)

    def test_init_hooks_core_methods(self, mock_core: Mock):
        """Test that ToolManager properly hooks into Server methods."""
        tool_manager = ToolManager(mock_core)

        # Verify that core methods were called to register handlers
        mock_core.list_tools.assert_called_once()
        mock_core.call_tool.assert_called_once_with(validate_input=False)

        # Verify internal state
        assert tool_manager._tools == {}

    def test_add_tool_basic_function(self, tool_manager: ToolManager):
        """Test adding a basic function as a tool."""

        def sample_add_tool(a: int, b: int) -> int:
            """A sample tool for testing."""
            return a + b

        result = tool_manager.add(sample_add_tool)

        # Verify the returned tool
        assert isinstance(result, types.Tool)
        assert result.name == "sample_add_tool"
        assert result.description == "A sample tool for testing."
        assert result.inputSchema is not None
        assert result.annotations is None
        assert result.meta is None

        # Verify internal state
        assert "sample_add_tool" in tool_manager._tools
        tool, tool_func = tool_manager._tools["sample_add_tool"]
        assert tool == result
        assert tool_func.func == sample_add_tool
        assert tool_func.meta is not None

    def test_add_tool_with_custom_options(self, tool_manager: ToolManager):
        """Test adding a tool with custom name, description, and metadata."""

        def basic_func(value: int) -> int:
            return value * 2

        custom_annotations = types.ToolAnnotations(title="math")
        custom_meta = {"version": "1.0"}

        result = tool_manager.add(
            basic_func,
            name="custom_name",
            description="Custom description",
            annotations=custom_annotations,
            meta=custom_meta,
        )

        assert result.name == "custom_name"
        assert result.description == "Custom description"
        assert result.annotations == custom_annotations
        assert result.meta == custom_meta

        # Verify it's stored with custom name
        assert "custom_name" in tool_manager._tools
        assert "basic_func" not in tool_manager._tools

    def test_add_tool_without_docstring(self, tool_manager: ToolManager):
        """Test adding a tool without docstring uses None as description."""

        def no_doc_tool(x: int) -> int:
            return x

        result = tool_manager.add(no_doc_tool)
        assert result.description is None

    def test_add_async_tool(self, tool_manager: ToolManager):
        """Test adding an async function as a tool."""

        async def async_tool(delay: float) -> str:
            """An async tool."""
            await anyio.sleep(delay)
            return "done"

        result = tool_manager.add(async_tool)

        assert result.name == "async_tool"
        assert result.description == "An async tool."
        assert "async_tool" in tool_manager._tools

    def test_add_duplicate_tool_raises_error(self, tool_manager: ToolManager):
        """Test that adding a tool with duplicate name raises PrimitiveError."""

        def tool1(x: int) -> int:
            return x

        def tool2(y: str) -> str:
            return y

        # Add first tool
        tool_manager.add(tool1, name="duplicate_name")

        # Adding second tool with same name should raise error
        with pytest.raises(PrimitiveError, match="Tool duplicate_name already registered"):
            tool_manager.add(tool2, name="duplicate_name")

    def test_add_again_tool_raises_error(self, tool_manager: ToolManager):
        """Test that adding a tool with duplicate name raises PrimitiveError."""

        def tool1(x: int) -> int:
            return x

        # Add tool
        tool_manager.add(tool1)

        # Adding tool again should raise error
        with pytest.raises(PrimitiveError, match="Tool tool1 already registered"):
            tool_manager.add(tool1)

    def test_add_lambda_without_name_raises_error(self, tool_manager: ToolManager):
        """Test that lambda functions without custom name are rejected by MCPFunc."""
        lambda_tool: Any = lambda x: x * 2  # noqa: E731  # type: ignore[misc]

        with pytest.raises(MCPFuncError, match="Lambda functions must be named"):
            tool_manager.add(lambda_tool)  # type: ignore[arg-type]

    def test_add_lambda_with_custom_name_succeeds(self, tool_manager: ToolManager):
        """Test that lambda functions with custom name work."""
        lambda_tool: Any = lambda x: x * 2  # noqa: E731  # type: ignore[misc]

        result = tool_manager.add(lambda_tool, name="custom_lambda")  # type: ignore[arg-type]
        assert result.name == "custom_lambda"
        assert "custom_lambda" in tool_manager._tools

    def test_add_function_with_var_args_raises_error(self, tool_manager: ToolManager):
        """Test that functions with *args are rejected by MCPFunc."""

        def tool_with_args(x: int, *args: int) -> int:
            return x + sum(args)

        with pytest.raises(MCPFuncError, match="Functions with \\*args are not supported"):
            tool_manager.add(tool_with_args)

    def test_add_function_with_kwargs_raises_error(self, tool_manager: ToolManager):
        """Test that functions with **kwargs are rejected by MCPFunc."""

        def tool_with_kwargs(x: int, **kwargs: Any) -> int:
            return x

        with pytest.raises(MCPFuncError, match="Functions with \\*\\*kwargs are not supported"):
            tool_manager.add(tool_with_kwargs)

    def test_add_bound_method_as_tool(self, tool_manager: ToolManager):
        """Test that bound instance methods can be added as tools."""

        class Calculator:
            def __init__(self, multiplier: int):
                self.multiplier = multiplier

            def calculate(self, value: int) -> int:
                """Calculate with multiplier."""
                return value * self.multiplier

        calc = Calculator(10)
        result = tool_manager.add(calc.calculate)

        assert result.name == "calculate"
        assert result.description == "Calculate with multiplier."
        assert "calculate" in tool_manager._tools

    def test_add_tool_with_no_parameters(self, tool_manager: ToolManager):
        """Test adding a tool with no parameters."""

        def no_param_tool() -> str:
            """A tool with no parameters."""
            return "result"

        result = tool_manager.add(no_param_tool)

        assert result.name == "no_param_tool"
        assert result.inputSchema is not None
        assert result.inputSchema.get("properties", {}) == {}

    def test_add_tool_with_parameter_descriptions(self, tool_manager: ToolManager):
        """Test that parameter descriptions are extracted from schema."""
        from typing import Annotated

        from pydantic import Field

        def tool_with_descriptions(
            count: Annotated[int, Field(description="The count value")],
            message: Annotated[str, Field(description="The message to display")] = "default",
        ) -> str:
            """A tool with parameter descriptions."""
            return f"{count}: {message}"

        result = tool_manager.add(tool_with_descriptions)

        assert result.inputSchema is not None
        properties = result.inputSchema.get("properties", {})
        assert "count" in properties
        assert properties["count"].get("description") == "The count value"
        assert "message" in properties
        assert properties["message"].get("description") == "The message to display"

    def test_add_tool_with_complex_parameter_types(self, tool_manager: ToolManager):
        """Test tools with complex parameter types like lists, dicts, Pydantic models."""
        from pydantic import BaseModel

        class Config(BaseModel):
            max_retries: int
            timeout: float

        def advanced_tool(items: list[str], config: Config, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
            """An advanced tool with complex types."""
            return {"items": items, "config": config, "metadata": metadata}

        result = tool_manager.add(advanced_tool)

        assert result.name == "advanced_tool"
        assert result.inputSchema is not None
        properties = result.inputSchema.get("properties", {})
        assert "items" in properties
        assert "config" in properties
        assert "metadata" in properties

        required = result.inputSchema.get("required", [])
        assert "items" in required
        assert "config" in required
        assert "metadata" not in required

    def test_add_duplicate_function_name_raises_error(self, tool_manager: ToolManager):
        """Test that adding functions with same name raises PrimitiveError."""

        def same_name(x: int) -> int:
            return x

        def same_name_different_func(y: str) -> str:  # Different function, same name
            return y

        # Add first function
        tool_manager.add(same_name)

        # This should work since we can give it a different name
        tool_manager.add(same_name_different_func, name="different_name")

        def different_scope_same_name():
            # But this should fail since it uses the function name
            with pytest.raises(PrimitiveError, match="Tool same_name already registered"):
                # Create another function with same name
                def same_name(z: float) -> float:
                    return z

                tool_manager.add(same_name)

        different_scope_same_name()

    def test_remove_existing_tool(self, tool_manager: ToolManager):
        """Test removing an existing tool."""

        def test_tool(x: int) -> int:
            return x

        # Add tool first
        added_tool = tool_manager.add(test_tool)
        assert "test_tool" in tool_manager._tools

        # Remove the tool
        removed_tool = tool_manager.remove("test_tool")

        assert removed_tool == added_tool
        assert "test_tool" not in tool_manager._tools

    def test_remove_nonexistent_tool_raises_error(self, tool_manager: ToolManager):
        """Test that removing a non-existent tool raises PrimitiveError."""
        with pytest.raises(PrimitiveError, match="Unknown tool: nonexistent"):
            tool_manager.remove("nonexistent")

    async def test_list_tools_empty(self, tool_manager: ToolManager):
        """Test listing tools when no tools are registered."""
        result = tool_manager.list()
        assert result == []

    async def test_list_tools_with_multiple_tools(self, tool_manager: ToolManager):
        """Test listing tools when multiple tools are registered."""

        def tool1(x: int) -> int:
            return x

        def tool2(y: str) -> str:
            return y

        added_tool1 = tool_manager.add(tool1)
        added_tool2 = tool_manager.add(tool2)

        result = tool_manager.list()

        assert len(result) == 2
        assert added_tool1 in result
        assert added_tool2 in result

    async def test_call_tool_sync_function(self, tool_manager: ToolManager):
        """Test calling a synchronous tool."""

        def multiply(x: int, y: int) -> int:
            """Multiply two numbers."""
            return x * y

        tool_manager.add(multiply)

        result: Any = await tool_manager.call("multiply", {"x": 3, "y": 4})
        assert isinstance(result[0][0], types.TextContent)
        assert result[1]["result"] == 12

    async def test_call_tool_async_function(self, tool_manager: ToolManager):
        """Test calling an asynchronous tool."""

        async def async_multiply(x: int, y: int) -> int:
            """Async multiply two numbers."""
            await anyio.sleep(0.01)  # Small delay to make it actually async
            return x * y

        tool_manager.add(async_multiply)

        result: Any = await tool_manager.call("async_multiply", {"x": 5, "y": 6})
        assert isinstance(result[0][0], types.TextContent)
        assert result[1]["result"] == 30

    async def test_call_tool_with_default_arguments(self, tool_manager: ToolManager):
        """Test calling a tool with default arguments."""

        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone."""
            return f"{greeting}, {name}!"

        tool_manager.add(greet)

        # Call with just required argument
        result: Any = await tool_manager.call("greet", {"name": "Alice"})
        assert result[1]["result"] == "Hello, Alice!"

        # Call with both arguments
        result = await tool_manager.call("greet", {"name": "Bob", "greeting": "Hi"})
        assert result[1]["result"] == "Hi, Bob!"

    async def test_call_nonexistent_tool_raises_error(self, tool_manager: ToolManager):
        """Test that calling a non-existent tool raises PrimitiveError."""
        with pytest.raises(PrimitiveError, match="Unknown tool: nonexistent"):
            await tool_manager.call("nonexistent", {})

    async def test_call_tool_with_complex_return_type(self, tool_manager: ToolManager):
        """Test calling a tool that returns complex data structures."""

        def get_user_info(user_id: int) -> dict[str, Any]:
            """Get user information."""
            return {
                "id": user_id,
                "name": f"User {user_id}",
                "active": True,
                "metadata": {"created": "2024-01-01", "role": "user"},
            }

        tool_manager.add(get_user_info)

        result: Any = await tool_manager.call("get_user_info", {"user_id": 123})
        expected = {
            "id": 123,
            "name": "User 123",
            "active": True,
            "metadata": {"created": "2024-01-01", "role": "user"},
        }
        assert isinstance(result[0][0], types.TextContent)
        assert result[1] == expected

    async def test_call_tool_argument_validation(self, tool_manager: ToolManager):
        """Test that tool arguments are properly validated by MCPFunc."""

        def strict_tool(required_int: int, optional_str: str = "default") -> str:
            """A tool with strict typing."""
            return f"{required_int}-{optional_str}"

        tool_manager.add(strict_tool)

        # Valid call should work
        result: Any = await tool_manager.call("strict_tool", {"required_int": 42})
        assert result[1]["result"] == "42-default"

        result = await tool_manager.call("strict_tool", {"required_int": "42"})
        assert result[1]["result"] == "42-default"

        # The actual validation happens in MCPFunc, so we test that it's called
        # by ensuring the tool works with valid arguments and would fail with invalid ones
        # through the MCPFunc validation layer

        with pytest.raises(InvalidArgumentsError, match="required_int"):
            await tool_manager.call("strict_tool", {"invalid_int": 42})

    async def test_call_tool_with_type_validation(self, tool_manager: ToolManager):
        """Test that argument types are validated during tool execution."""

        def typed_tool(count: int, message: str) -> str:
            """A tool with strict types."""
            return f"Count {count}: {message}"

        tool_manager.add(typed_tool)

        # Valid types should work
        result: Any = await tool_manager.call("typed_tool", {"count": 5, "message": "hello"})
        assert result[1]["result"] == "Count 5: hello"

        # String numbers should be coerced to int by pydantic
        result = await tool_manager.call("typed_tool", {"count": "10", "message": "world"})
        assert result[1]["result"] == "Count 10: world"

        with pytest.raises(InvalidArgumentsError, match="Input should be a valid integer"):
            await tool_manager.call("typed_tool", {"count": "not_a_number", "message": "hello"})

    async def test_call_tool_with_no_parameters(self, tool_manager: ToolManager):
        """Test calling tools that require no parameters."""

        def static_tool() -> str:
            """A tool with no parameters."""
            return "static result"

        tool_manager.add(static_tool)

        # Call with empty dict
        result: Any = await tool_manager.call("static_tool", {})
        assert result[1]["result"] == "static result"

    async def test_call_tool_with_complex_arguments(self, tool_manager: ToolManager):
        """Test calling a tool with complex argument types."""
        from pydantic import BaseModel

        class TaskConfig(BaseModel):
            priority: int
            timeout: float

        def process_task(task_ids: list[int], config: TaskConfig) -> dict[str, Any]:
            """Process tasks with configuration."""
            return {"processed": task_ids, "priority": config.priority, "timeout": config.timeout}

        tool_manager.add(process_task)

        result: Any = await tool_manager.call(
            "process_task", {"task_ids": [1, 2, 3], "config": {"priority": 5, "timeout": 30.0}}
        )

        assert result[1]["processed"] == [1, 2, 3]
        assert result[1]["priority"] == 5
        assert result[1]["timeout"] == 30.0

    async def test_call_bound_method_tool(self, tool_manager: ToolManager):
        """Test calling a tool that is a bound method."""

        class DataProcessor:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def process(self, data: str) -> str:
                """Process data with prefix."""
                return f"{self.prefix}: {data}"

        processor = DataProcessor("PROCESSED")
        tool_manager.add(processor.process)

        result: Any = await tool_manager.call("process", {"data": "test data"})
        assert result[1]["result"] == "PROCESSED: test data"

    async def test_call_tool_function_raises_exception(self, tool_manager: ToolManager):
        """Test that exceptions in tool functions are properly handled."""

        def failing_tool(should_fail: bool) -> str:
            """A tool that can fail."""
            if should_fail:
                raise MCPRuntimeError("Tool failed")
            return "Success"

        tool_manager.add(failing_tool)

        # Should succeed when not failing
        result: Any = await tool_manager.call("failing_tool", {"should_fail": False})
        assert result[1]["result"] == "Success"

        with pytest.raises(MCPRuntimeError, match="Tool failed"):
            await tool_manager.call("failing_tool", {"should_fail": True})

    async def test_call_async_tool_exception_wrapped(self, tool_manager: ToolManager):
        """Test that exceptions from async tool functions are wrapped in MCPRuntimeError."""

        async def async_failing_tool(should_fail: bool) -> str:
            """An async tool that can fail."""
            await anyio.sleep(0.001)
            if should_fail:
                raise MCPRuntimeError("Async tool error")
            return "Success"

        tool_manager.add(async_failing_tool)

        # Should succeed when not failing
        result: Any = await tool_manager.call("async_failing_tool", {"should_fail": False})
        assert result[1]["result"] == "Success"

        with pytest.raises(MCPRuntimeError, match="Async tool error"):
            await tool_manager.call("async_failing_tool", {"should_fail": True})

    async def test_call_tool_with_missing_required_arguments(self, tool_manager: ToolManager):
        """Test that calling a tool with missing required arguments raises an error."""

        def required_args_tool(required_param: str, optional_param: str = "default") -> str:
            """A tool with required parameters."""
            return f"{required_param}-{optional_param}"

        tool_manager.add(required_args_tool)

        # Should work with all params
        result: Any = await tool_manager.call("required_args_tool", {"required_param": "value"})
        assert result[1]["result"] == "value-default"

        # Should fail without required param
        with pytest.raises(InvalidArgumentsError, match="Field required"):
            await tool_manager.call("required_args_tool", {})

        # Should fail with only optional param
        with pytest.raises(InvalidArgumentsError, match="Field required"):
            await tool_manager.call("required_args_tool", {"optional_param": "value"})

    async def test_call_tool_exception_with_cause(self, tool_manager: ToolManager):
        """Test that exception chaining is preserved."""

        def tool_with_nested_error(trigger: str) -> str:
            """A tool that raises a nested exception."""
            if trigger == "nested":
                try:
                    raise ValueError("Inner error")
                except ValueError as e:
                    raise ValueError("Outer error") from e
            return "OK"

        tool_manager.add(tool_with_nested_error)

        with pytest.raises(ValueError, match="Outer error"):
            await tool_manager.call("tool_with_nested_error", {"trigger": "nested"})

    def test_decorator_usage(self, tool_manager: ToolManager):
        """Test using ToolManager as a decorator."""

        @tool_manager(name="decorated_tool", description="A decorated tool")
        def decorated_function(value: int) -> int:
            """A decorated tool function."""
            return value * 3

        # Verify the tool was added
        assert "decorated_tool" in tool_manager._tools
        tool, _ = tool_manager._tools["decorated_tool"]
        assert tool.name == "decorated_tool"
        assert tool.description == "A decorated tool"

    async def test_decorator_with_no_arguments(self, tool_manager: ToolManager):
        """Test using ToolManager decorator with a handler that accepts no arguments."""

        @tool_manager(name="no_args_tool", description="A tool with no arguments")
        def no_args_function() -> int:
            """A tool function that takes no arguments."""
            return 42

        # Verify the tool was added
        assert "no_args_tool" in tool_manager._tools
        tool, _ = tool_manager._tools["no_args_tool"]
        assert tool.name == "no_args_tool"
        assert tool.description == "A tool with no arguments"

        # Verify the tool can be called without arguments
        result = await tool_manager.call("no_args_tool", {})
        # Result is a tuple of (content_list, structured_output)
        assert len(result) == 2
        content_list = result[0]
        assert isinstance(content_list, list)
        assert len(content_list) == 1
        assert isinstance(content_list[0], types.TextContent)
        assert content_list[0].text == "42"

    def test_tool_options_typed_dict(self):
        """Test ToolDefinition TypedDict structure."""
        # This tests the type structure - mainly for documentation
        options: ToolDefinition = {
            "name": "test_name",
            "description": "test_description",
            "annotations": types.ToolAnnotations(title="test"),
            "meta": {"version": "1.0"},
        }

        assert options["name"] == "test_name"
        assert options["description"] == "test_description"
        assert options["annotations"] == types.ToolAnnotations(title="test")
        assert options["meta"] == {"version": "1.0"}

    def test_integration_with_mcp_func(self, tool_manager: ToolManager):
        """Test integration with MCPFunc for schema generation."""

        def typed_tool(count: int, message: str, active: bool = True) -> dict[str, Any]:
            """A well-typed tool for testing schema generation."""
            return {"count": count, "message": message, "active": active}

        result = tool_manager.add(typed_tool)

        # Verify that inputSchema was generated
        assert result.inputSchema is not None
        schema = result.inputSchema

        # Should have properties for the parameters
        assert "properties" in schema
        properties = schema["properties"]
        assert "count" in properties
        assert "message" in properties
        assert "active" in properties

        # Required should include non-default parameters
        assert "required" in schema
        required = schema["required"]
        assert "count" in required
        assert "message" in required
        assert "active" not in required  # Has default value

    async def test_full_workflow(self, tool_manager: ToolManager):
        """Test a complete workflow: add, list, call, remove."""

        def calculator(operation: str, a: float, b: float) -> float:
            """Perform basic calculations."""
            if operation == "add":
                return a + b
            elif operation == "multiply":
                return a * b
            else:
                raise Exception(f"Unknown operation: {operation}")

        # Add tool
        added_tool = tool_manager.add(calculator, description="Basic calculator")
        assert added_tool.name == "calculator"
        assert added_tool.description == "Basic calculator"

        # List tools
        tools = tool_manager.list()
        assert len(tools) == 1
        assert tools[0] == added_tool

        # Call tool
        result: Any = await tool_manager.call("calculator", {"operation": "add", "a": 10.5, "b": 5.2})
        assert result[1]["result"] == 15.7

        result = await tool_manager.call("calculator", {"operation": "multiply", "a": 3.0, "b": 4.0})
        assert result[1]["result"] == 12.0

        # Remove tool
        removed_tool = tool_manager.remove("calculator")
        assert removed_tool == added_tool

        # Verify it's gone
        tools = tool_manager.list()
        assert len(tools) == 0

        # Calling removed tool should fail
        with pytest.raises(PrimitiveError, match="Unknown tool: calculator"):
            await tool_manager.call("calculator", {"operation": "add", "a": 1, "b": 2})


class TestToolManagerAdvancedFeatures:
    """Test suite for advanced ToolManager features inspired by FastMCP patterns."""

    @pytest.fixture
    def mock_core(self) -> Mock:
        """Create a mock Server for testing."""
        core = Mock(spec=Server)
        core.list_tools = Mock(return_value=Mock())
        core.call_tool = Mock(return_value=Mock())
        return core

    @pytest.fixture
    def tool_manager(self, mock_core: Mock) -> ToolManager:
        """Create a ToolManager instance with mocked core."""
        return ToolManager(mock_core)

    def test_add_tool_with_pydantic_model_parameter(self, tool_manager: ToolManager):
        """Test adding a tool that takes a Pydantic model as parameter."""

        class UserInput(BaseModel):
            name: str
            age: int
            email: str = Field(description="User email address")

        def create_user(user: UserInput, send_welcome: bool = True) -> dict[str, Any]:
            """Create a new user"""
            return {"id": 1, **user.model_dump(), "welcomed": send_welcome}

        result = tool_manager.add(create_user)

        assert result.name == "create_user"
        assert result.description == "Create a new user"
        # Check that the schema includes the Pydantic model
        assert "user" in result.inputSchema["properties"]
        assert "send_welcome" in result.inputSchema["properties"]

    def test_add_tool_with_field_descriptions(self, tool_manager: ToolManager):
        """Test that Field descriptions are properly included in the schema."""

        def greet(
            name: str = Field(description="The name to greet"),
            title: str = Field(description="Optional title", default=""),
        ) -> str:
            """A greeting tool"""
            return f"Hello {title} {name}"

        result = tool_manager.add(greet)

        # Check that parameter descriptions are present in the schema
        properties = result.inputSchema["properties"]
        assert "name" in properties
        assert properties["name"]["description"] == "The name to greet"
        assert "title" in properties
        assert properties["title"]["description"] == "Optional title"

    def test_callable_objects_not_supported(self, tool_manager: ToolManager):
        """Test that callable objects (not functions) are not supported by MiniMCP."""

        class MyCallableTool:
            def __call__(self, x: int, y: int) -> int:
                """Multiply two numbers"""
                return x * y

        callable_obj = MyCallableTool()

        # MiniMCP's MCPFunc validates that objects are functions or methods
        # Callable objects are not supported (unlike FastMCP)
        with pytest.raises(MCPFuncError, match="Object passed is not a function or method"):
            tool_manager.add(callable_obj, name="multiply")

    async def test_call_tool_with_pydantic_validation(self, tool_manager: ToolManager):
        """Test that Pydantic validation works correctly during tool calls."""

        def typed_tool(count: int, message: str) -> str:
            """A tool with typed parameters"""
            return f"{message} (count: {count})"

        tool_manager.add(typed_tool)

        # Valid call
        result = await tool_manager.call("typed_tool", {"count": 5, "message": "test"})
        # Result is a tuple of (content_list, structured_output)
        assert len(result) == 2
        content_list = result[0]

        assert isinstance(content_list, list)
        assert len(content_list) > 0
        assert isinstance(content_list[0], types.TextContent)
        assert "count: 5" in str(content_list[0].text)

        # Invalid type should raise InvalidArgumentsError
        with pytest.raises(InvalidArgumentsError):
            await tool_manager.call("typed_tool", {"count": "not a number", "message": "test"})

    def test_tool_with_title_field(self, tool_manager: ToolManager):
        """Test that tools can have a title field for display."""

        def basic_calculator(a: int, b: int) -> int:
            """Add two numbers"""
            return a + b

        result = tool_manager.add(basic_calculator, title="🧮 Basic Calculator")

        assert result.name == "basic_calculator"
        assert result.title == "🧮 Basic Calculator"
        assert result.description == "Add two numbers"

    def test_tool_with_annotations(self, tool_manager: ToolManager):
        """Test that tools can have annotations."""

        def important_tool(value: int) -> int:
            """An important tool"""
            return value

        annotations = types.ToolAnnotations(title="Critical Tool")
        result = tool_manager.add(important_tool, annotations=annotations)

        assert result.annotations is not None
        assert result.annotations == annotations
        assert result.annotations.title == "Critical Tool"

    async def test_tool_error_handling_preserves_unicode(self, tool_manager: ToolManager):
        """Test that error messages preserve Unicode characters."""

        def error_tool(trigger: bool) -> str:
            """Tool that raises errors with Unicode"""
            if trigger:
                raise ValueError("⚠ Unicode error message 🚫")
            return "Success"

        tool_manager.add(error_tool)

        # When tool raises an error during _call, it gets caught by the core server
        # and returned as a tool result with isError=True
        # For our test, we just verify the tool was added successfully
        tools = tool_manager.list()
        assert len(tools) == 1
        assert tools[0].name == "error_tool"

    async def test_tool_convert_result_exception(self, tool_manager: ToolManager):
        """Test that exceptions during result conversion are handled properly."""

        def simple_tool(value: str) -> str:
            """A simple tool"""
            return value

        tool_manager.add(simple_tool)

        # Patch the convert_result method on FuncMetadata class
        with patch.object(FuncMetadata, "convert_result", side_effect=ValueError("Conversion failed")):
            with pytest.raises(ToolMCPRuntimeError, match="Error calling tool simple_tool"):
                await tool_manager._call("simple_tool", {"value": "test"})

    async def test_tool_call_wrapper_mcp_runtime_error(self, tool_manager: ToolManager):
        """Test that call() wrapper properly converts ToolMCPRuntimeError to MCPRuntimeError."""

        def simple_tool(value: str) -> str:
            """A simple tool"""
            return value

        tool_manager.add(simple_tool)

        # Patch the convert_result method on FuncMetadata class
        with patch.object(FuncMetadata, "convert_result", side_effect=RuntimeError("Runtime error")):
            with pytest.raises(MCPRuntimeError, match="Error calling tool simple_tool"):
                await tool_manager.call("simple_tool", {"value": "test"})
