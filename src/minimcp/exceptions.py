from typing import Any

from minimcp.types import Message

# --- External Errors ---------------------------------------------


class MiniMCPError(Exception):
    """
    Base for all MiniMCP errors that would be exposed externally.
    """

    pass


class MiniMCPJSONRPCError(MiniMCPError):
    """
    Base exception for all MiniMCP errors with a MCP response message.
    They must be handled by the transport layer to be returned to the client.
    """

    response: Message

    def __init__(self, error_message: str, response: Message):
        super().__init__(error_message)
        self.response = response


class InvalidMessageError(MiniMCPJSONRPCError):
    """Invalid message error - The message is not a valid JSON-RPC message."""

    pass


class ContextError(MiniMCPError):
    """
    Context error - Raised when when context access fails. Can be caused by:
    - No Context: Called get outside of an active context.
    - Scope is not available in current context.
    - Responder is not available in current context.
    """

    pass


class MCPFuncError(MiniMCPError):
    """Raised when an error occurs inside an MCP function."""

    pass


class PrimitiveError(MiniMCPError):
    """
    Raised when an error is encountered while adding, retrieving
    or removing a primitive (prompt, resource, tool)
    """

    pass


# --- Internal Errors ---------------------------------------------


class InternalMCPError(Exception):
    """
    These errors are raised and managed by MiniMCP internally,
    and are not expected to be exposed externally - Neither inside the handlers nor the transport layer.
    """

    data: dict[str, Any] | None = None

    def __init__(self, message: str, data: dict[str, Any] | None = None):
        super().__init__(message, data)
        self.data = data


class InvalidJSONError(InternalMCPError):
    """Raised when the message is not a valid JSON string."""

    pass


class InvalidJSONRPCMessageError(InternalMCPError):
    """Raised when the message is not valid JSON-RPC object."""

    pass


class InvalidMCPMessageError(InternalMCPError):
    """Raised when the message is not a valid MCP message."""

    pass


class InvalidArgumentsError(InternalMCPError):
    """Invalid arguments error - Caused by pydantic ValidationError."""

    pass


class UnsupportedMessageTypeError(InternalMCPError):
    """
    Unsupported message type received
    MiniMCP expects the incoming message to be a JSONRPCRequest or JSONRPCNotification.
    """

    pass


class RequestHandlerNotFoundError(InternalMCPError):
    """
    The client request does not have a handler registered in the MiniMCP server.
    Handlers are registered per request type.
    Request types: PingRequest, InitializeRequest, CompleteRequest, SetLevelRequest,
        GetPromptRequest, ListPromptsRequest, ListResourcesRequest, ListResourceTemplatesRequest,
        ReadResourceRequest, SubscribeRequest, UnsubscribeRequest, CallToolRequest, ListToolsRequest
    """

    pass


class ResourceNotFoundError(InternalMCPError):
    """Resource not found error - Raised when a resource is not found."""

    pass


class MCPRuntimeError(InternalMCPError):
    """MCP runtime error - Raised when a runtime error occurs."""

    pass


# --- Special Tool Errors ---------------------------------------------
# These exceptions inherit from BaseException (not Exception) to bypass the low-level
# server's default exception handler during tool execution. This allows the tool manager
# to implement custom error handling and response formatting


class SpecialToolError(BaseException):
    pass


class ToolPrimitiveError(SpecialToolError):
    pass


class ToolInvalidArgumentsError(SpecialToolError):
    pass


class ToolMCPRuntimeError(SpecialToolError):
    pass
