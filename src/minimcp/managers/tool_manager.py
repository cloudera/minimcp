import builtins
import logging
from collections.abc import Callable
from functools import partial
from typing import Any

import mcp.types as types
from mcp.server.lowlevel.server import CombinationContent, Server
from typing_extensions import TypedDict, Unpack

from minimcp.exceptions import (
    InvalidArgumentsError,
    MCPRuntimeError,
    PrimitiveError,
    ToolInvalidArgumentsError,
    ToolMCPRuntimeError,
    ToolPrimitiveError,
)
from minimcp.utils.mcp_func import MCPFunc

logger = logging.getLogger(__name__)


class ToolDefinition(TypedDict, total=False):
    """
    Type definition for tool parameters.

    Attributes:
        name: Optional unique identifier for the tool. If not provided, the function name is used.
            Must be unique across all tools in the server.
        title: Optional human-readable name for display purposes. Shows in client UIs to help users
            understand which tools are being exposed to the AI model.
        description: Optional human-readable description of tool functionality. If not provided,
            the function's docstring is used.
        annotations: Optional annotations describing tool behavior. For trust & safety, clients must
            consider annotations untrusted unless from trusted servers.
        meta: Optional metadata dictionary for additional tool information.
    """

    name: str | None
    title: str | None
    description: str | None
    annotations: types.ToolAnnotations | None
    meta: dict[str, Any] | None


class ToolManager:
    """
    ToolManager is responsible for registration and execution of MCP tool handlers.

    The Model Context Protocol (MCP) allows servers to expose tools that can be invoked by language
    models. Tools enable models to interact with external systems, such as querying databases, calling
    APIs, or performing computations. Each tool is uniquely identified by a name and includes metadata
    describing its schema.

    The ToolManager can be used as a decorator (@mcp.tool()) or programmatically via the mcp.tool.add(),
    mcp.tool.list(), mcp.tool.call() and mcp.tool.remove() methods.

    When a tool handler is added, its name and description are automatically inferred from the handler
    function. You can override these by passing explicit parameters. The inputSchema and outputSchema
    are automatically generated from function type annotations. Tools support both structured and
    unstructured content in results.

    Tool results can contain multiple content types (text, image, audio, resource links, embedded
    resources) and support optional annotations. All content types support annotations for metadata
    about audience, priority, and modification times.

    For more details, see: https://modelcontextprotocol.io/specification/2025-06-18/server/tools

    Example:
        @mcp.tool()
        def get_weather(location: str) -> str:
            '''Get current weather information for a location'''
            return f"Weather in {location}: 72°F, Partly cloudy"

        # With display title and annotations
        @mcp.tool(title="Weather Information Provider", annotations={"priority": 0.9})
        def get_weather(location: str) -> dict:
            '''Get current weather data for a location'''
            return {"temperature": 72, "conditions": "Partly cloudy"}

        # Or programmatically:
        mcp.tool.add(get_weather, title="Weather Provider")
    """

    _tools: dict[str, tuple[types.Tool, MCPFunc]]

    def __init__(self, core: Server):
        """
        Args:
            core: The low-level MCP Server instance to hook into.
        """
        self._tools = {}
        self._hook_core(core)

    def _hook_core(self, core: Server) -> None:
        """Register tool handlers with the MCP core server.

        Args:
            core: The low-level MCP Server instance to hook into.
        """
        core.list_tools()(self._async_list)

        # Validation done by func_meta in call. Hence passing validate_input=False
        # TODO: Ensure only one validation is required
        core.call_tool(validate_input=False)(self._call)

    def __call__(self, **kwargs: Unpack[ToolDefinition]) -> Callable[[types.AnyFunction], types.Tool]:
        """Decorator to add/register a tool handler at the time of handler function definition.

        Tool name and description are automatically inferred from the handler function. You can override
        these by passing explicit parameters (name, title, description, annotations, meta). The inputSchema
        and outputSchema are automatically generated from function type annotations.

        Args:
            **kwargs: Optional tool definition parameters (name, title, description, annotations, meta).
                Parameters are defined in the ToolDefinition class.

        Returns:
            A decorator function that adds the tool handler.

        Example:
            @mcp.tool(title="Weather Information Provider")
            def get_weather(location: str) -> dict:
                return {"temperature": 72, "conditions": "Partly cloudy"}
        """
        return partial(self.add, **kwargs)

    def add(self, func: types.AnyFunction, **kwargs: Unpack[ToolDefinition]) -> types.Tool:
        """To programmatically add/register a tool handler function.

        This is useful when the handler function is already defined and you have a function object
        that needs to be registered at runtime.

        If not provided, the tool name (unique identifier) and description are automatically inferred
        from the function's name and docstring. The title field should be provided for better display
        in client UIs. The inputSchema and outputSchema are automatically generated from function type
        annotations using Pydantic models for validation.

        Handler functions can return various content types:
        - Unstructured content: str, bytes, list of content blocks
        - Structured content: dict (returned in structuredContent field)
        - Combination: tuple of (unstructured, structured)

        Tool results support multiple content types per MCP specification:
        - Text content (type: "text")
        - Image content (type: "image") - base64-encoded
        - Audio content (type: "audio") - base64-encoded
        - Resource links (type: "resource_link")
        - Embedded resources (type: "resource")

        Args:
            func: The tool handler function. Can be synchronous or asynchronous. Should return
                content that can be converted to tool result format.
            **kwargs: Optional tool definition parameters to override inferred values
                (name, title, description, annotations, meta). Parameters are defined in
                the ToolDefinition class.

        Returns:
            The registered Tool object with unique identifier, inputSchema, optional outputSchema,
            and optional annotations.

        Raises:
            PrimitiveError: If a tool with the same name is already registered
            MCPFuncError: If the function cannot be used as a MCP handler function
        """

        tool_func = MCPFunc(func, kwargs.get("name"))
        if tool_func.name in self._tools:
            raise PrimitiveError(f"Tool {tool_func.name} already registered")

        tool = types.Tool(
            name=tool_func.name,
            title=kwargs.get("title", None),
            description=kwargs.get("description", tool_func.doc),
            inputSchema=tool_func.input_schema,
            outputSchema=tool_func.output_schema,
            annotations=kwargs.get("annotations", None),
            _meta=kwargs.get("meta", None),
        )

        self._tools[tool_func.name] = (tool, tool_func)
        logger.debug("Tool %s added", tool_func.name)

        return tool

    def remove(self, name: str) -> types.Tool:
        """Remove a tool by name.

        Args:
            name: The name of the tool to remove.

        Returns:
            The removed Tool object.

        Raises:
            PrimitiveError: If the tool is not found.
        """
        if name not in self._tools:
            # Raise INVALID_PARAMS as per MCP specification
            raise PrimitiveError(f"Unknown tool: {name}")

        logger.debug("Removing tool %s", name)
        return self._tools.pop(name)[0]

    async def _async_list(self) -> builtins.list[types.Tool]:
        """Async wrapper for list().

        Returns:
            A list of all registered Tool objects.
        """
        return self.list()

    def list(self) -> builtins.list[types.Tool]:
        """List all registered tools.

        Returns:
            A list of all registered Tool objects.
        """
        return [tool[0] for tool in self._tools.values()]

    async def _call(self, name: str, args: dict[str, Any]) -> CombinationContent:
        """Execute a tool by name, as specified in the MCP tools/call protocol.

        This method handles the MCP tools/call request, executing the tool handler function with
        the provided arguments. Arguments are validated against the tool's inputSchema, and the
        result is converted to the appropriate tool result format per the MCP specification.

        Tools use two error reporting mechanisms per the spec:
        1. Protocol Errors: Raised as a ToolPrimitiveError, ToolInvalidArgumentsError or ToolMCPRuntimeErrors
        2. Tool Execution Errors: Returned in result with isError=true (handled by lowlevel server)

        Errors raised are of SpecialToolErrors type. SpecialToolErrors inherit from BaseException (not Exception)
        to bypass the low-level server's default exception handler during tool execution. This allows
        the tool manager to implement custom error handling and response formatting.

        The result can contain:
        - Unstructured content: Array of content blocks (text, image, audio, resource links, embedded resources)
        - Structured content: JSON object (if outputSchema is defined)
        - Combination: Both unstructured and structured content

        Args:
            name: The unique identifier of the tool to call.
            args: Dictionary of arguments to pass to the tool handler. Must conform to the
                tool's inputSchema. Arguments are validated by MCPFunc.

        Returns:
            CombinationContent containing either unstructured content, structured content, or both,
            per the MCP protocol.

        Raises:
            ToolPrimitiveError: If the tool is not found (maps to -32602 Invalid params per spec).
            ToolInvalidArgumentsError: If the tool arguments are invalid.
            ToolMCPRuntimeError: If an error occurs during tool execution (maps to -32603 Internal error).
                Note: Tool execution errors (API failures, invalid input data, business logic errors)
                are handled by the lowlevel server and returned with isError=true.
        """
        if name not in self._tools:
            # Raise INVALID_PARAMS as per MCP specification
            raise ToolPrimitiveError(f"Unknown tool: {name}")

        tool_func = self._tools[name][1]

        try:
            # Exceptions on execution are captured by the core and returned as part of CallToolResult.
            result = await tool_func.execute(args)
            logger.debug("Tool %s handled with args %s", name, args)
        except InvalidArgumentsError as e:
            raise ToolInvalidArgumentsError(str(e)) from e

        try:
            return tool_func.meta.convert_result(result)
        except Exception as e:
            msg = f"Error calling tool {name}: {e}"
            logger.exception(msg)
            raise ToolMCPRuntimeError(msg) from e

    async def call(self, name: str, args: dict[str, Any]) -> CombinationContent:
        """
        Wrapper for _call so that the tools can be called manually by the user. It converts
        the SpecialToolErrors to the appropriate MiniMCPError.

        SpecialToolErrors inherit from BaseException (not Exception) to bypass the low-level
        server's default exception handler during tool execution. This allows the tool manager
        to implement custom error handling and response formatting.

        Args:
            name: The unique identifier of the tool to call.
            args: Dictionary of arguments to pass to the tool handler. Must conform to the
                tool's inputSchema. Arguments are validated by MCPFunc.

        Returns:
            CombinationContent containing either unstructured content, structured content, or both,
            per the MCP protocol.

        Raises:
            PrimitiveError: If the tool is not found.
            InvalidArgumentsError: If the tool arguments are invalid.
            MCPRuntimeError: If an error occurs during tool execution.
        """

        try:
            return await self._call(name, args)
        except ToolPrimitiveError as e:
            raise PrimitiveError(str(e)) from e
        except ToolInvalidArgumentsError as e:
            raise InvalidArgumentsError(str(e)) from e
        except ToolMCPRuntimeError as e:
            raise MCPRuntimeError(str(e)) from e
