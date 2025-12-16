import logging
import uuid
from typing import Any, Generic

import anyio
import mcp.shared.version as version
import mcp.types as types
from mcp.server.lowlevel.server import NotificationOptions, Server
from pydantic import ValidationError

import minimcp.utils.json_rpc as json_rpc
from minimcp.exceptions import (
    ContextError,
    InternalMCPError,
    InvalidArgumentsError,
    InvalidJSONError,
    InvalidJSONRPCMessageError,
    InvalidMCPMessageError,
    InvalidMessageError,
    MCPRuntimeError,
    PrimitiveError,
    RequestHandlerNotFoundError,
    ResourceNotFoundError,
    ToolInvalidArgumentsError,
    ToolMCPRuntimeError,
    ToolPrimitiveError,
    UnsupportedMessageTypeError,
)
from minimcp.limiter import Limiter
from minimcp.managers.context_manager import Context, ContextManager, ScopeT
from minimcp.managers.prompt_manager import PromptManager
from minimcp.managers.resource_manager import ResourceManager
from minimcp.managers.tool_manager import ToolManager
from minimcp.responder import Responder
from minimcp.types import RESOURCE_NOT_FOUND, Message, NoMessage, Send

logger = logging.getLogger(__name__)


class MiniMCP(Generic[ScopeT]):
    """
    MiniMCP is the key orchestrator for building Model Context Protocol (MCP) servers.

    MiniMCP provides a high-level, stateless API for implementing MCP servers that expose tools,
    prompts, and resources to language models. It handles the complete message lifecycle from
    parsing and validation through handler execution and error formatting, while managing
    concurrency limits and idle timeouts.

    Architecture:
        MiniMCP integrates several specialized managers to provide its functionality:
        - tool: ToolManager for registering and executing tool handlers
        - prompt: PromptManager for exposing prompt templates to clients
        - resource: ResourceManager for providing contextual data to language models
        - context: ContextManager for accessing request metadata within handlers

    Key Features:
        - Message Processing: Parses JSON-RPC messages, validates against MCP protocol specification,
          and dispatches to appropriate handlers based on request type
        - Concurrency Control: Enforces configurable limits on concurrent message handlers and
          idle timeouts to prevent resource exhaustion
        - Context Management: Maintains thread-safe, async-safe context isolation using contextvars,
          providing handlers with access to message metadata, scope objects, and responder for
          bidirectional communication
        - Error Handling: Centralizes error processing with automatic conversion to JSON-RPC error
          responses, mapping MiniMCP exceptions to appropriate MCP error codes
        - Protocol Compliance: Implements MCP handshake (initialize request/response) with protocol
          version negotiation and capability advertisement

    Generic Parameter:
        ScopeT: Optional type for custom scope objects passed to handlers. Use this to provide
            authentication details, user info, session data, database handles, or any other
            per-request context to your handlers. Set to None if not needed.

    Example:
        ```python
        from minimcp import MiniMCP

        # Create server instance
        mcp = MiniMCP("my-server", version="1.0.0")

        # Register a tool
        @mcp.tool()
        def calculate(expression: str) -> float:
            '''Evaluate a mathematical expression'''
            return eval(expression)

        # Register a prompt
        @mcp.prompt()
        def code_review(code: str) -> str:
            '''Request a code review'''
            return f"Please review this code:\n{code}"

        # Register a resource
        @mcp.resource("config://app.json")
        def get_config() -> dict:
            return {"version": "1.0", "environment": "production"}

        # Handle incoming messages
        response = await mcp.handle(message, send=send_callback, scope=user_context)
        ```

    For transport integration, use with HTTPTransport, StreamableHTTPTransport, or StdioTransport.
    See https://modelcontextprotocol.io/specification/2025-06-18 for protocol details.
    """

    _core: Server
    _notification_options: NotificationOptions | None = None
    _limiter: Limiter
    _include_stack_trace: bool

    tool: ToolManager
    prompt: PromptManager
    resource: ResourceManager
    context: ContextManager[ScopeT]

    def __init__(
        self,
        name: str,
        version: str | None = None,
        instructions: str | None = None,
        idle_timeout: int = 30,
        max_concurrency: int = 100,
        include_stack_trace: bool = False,
    ) -> None:
        """
        Initialize the MCP server.

        Args:
            name: The name of the MCP server.
            version: The version of the MCP server.
            instructions: The instructions for the MCP server.

            idle_timeout: Time in seconds after which a message handler will be considered idle and
                timed out. Default is 30 seconds.
            max_concurrency: The maximum number of message handlers that could be run at the same time,
                beyond which the handle() calls will be blocked. Default is 100.
            include_stack_trace: Whether to include the stack trace in the error response. Default is False.
        """
        self._limiter = Limiter(idle_timeout, max_concurrency)
        self._include_stack_trace = include_stack_trace

        # TODO: Add support for server-to-client notifications
        self._notification_options = NotificationOptions(
            prompts_changed=False,
            resources_changed=False,
            tools_changed=False,
        )

        # Setup core
        self._core = Server[Any, Any](name=name, version=version, instructions=instructions)
        self._core.request_handlers[types.InitializeRequest] = self._initialize_handler
        # MiniMCP handles InitializeRequest but not InitializedNotification as it is stateless

        # Setup managers
        self.tool = ToolManager(self._core)
        self.prompt = PromptManager(self._core)
        self.resource = ResourceManager(self._core)

        self.context = ContextManager[ScopeT]()

    # --- Properties ---
    @property
    def name(self) -> str:
        """The name of the MCP server."""
        return self._core.name

    @property
    def instructions(self) -> str | None:
        """The instructions for the MCP server."""
        return self._core.instructions

    @property
    def version(self) -> str | None:
        """The version of the MCP server."""
        return self._core.version

    # --- Handlers ---
    async def handle(
        self, message: Message, send: Send | None = None, scope: ScopeT | None = None
    ) -> Message | NoMessage:
        """
        Handle an incoming MCP message from the client. It is the entry point for all MCP messages and runs
        on the current event loop task.

        It is responsible for parsing the message, validating the message, enforcing limiters, activating the
        context, and dispatching the message to the appropriate handler. It also provides a centralized error
        handling mechanism for all MCP errors.

        Args:
            message: The incoming MCP message from the client.
            send: The send function for transmitting messages to the client. Optional.
            scope: The scope object for the client. Optional.

        Returns:
            The response MCP message to the client. If the message is a notification, NoMessage.NOTIFICATION
            is returned.

        Raises:
            InvalidMessageError: If the message is not a valid JSON-RPC message.
            cancelled_exception_class: If the task is cancelled.
        """
        try:
            rpc_msg = self._parse_message(message)

            async with self._limiter() as time_limiter:
                responder = Responder(message, send, time_limiter) if send else None
                context = Context[ScopeT](message=rpc_msg, time_limiter=time_limiter, scope=scope, responder=responder)
                with self.context.active(context):
                    return await self._handle_rpc_msg(rpc_msg)

        # --- Centralized MCP error handling - Handles all internal MCP errors ---
        # - Exception raised - InvalidMessageFormatError from ParseError or InvalidJSONRPCMessageError
        # - Other exceptions will be formatted and returned as JSON-RPC response.
        # - Errors inside each tool call will be handled by the core and returned as part of CallToolResult.
        except InvalidJSONError as e:
            response = self._process_error(e, message, types.PARSE_ERROR)
            raise InvalidMessageError(str(e), response) from e
        except InvalidJSONRPCMessageError as e:
            response = self._process_error(e, message, types.INVALID_REQUEST)
            raise InvalidMessageError(str(e), response) from e
        except UnsupportedMessageTypeError as e:
            return self._process_error(e, message, types.INVALID_REQUEST)
        except (
            InvalidMCPMessageError,
            InvalidArgumentsError,
            PrimitiveError,
            ToolInvalidArgumentsError,
            ToolPrimitiveError,
        ) as e:
            return self._process_error(e, message, types.INVALID_PARAMS)
        except RequestHandlerNotFoundError as e:
            return self._process_error(e, message, types.METHOD_NOT_FOUND)
        except ResourceNotFoundError as e:
            return self._process_error(e, message, RESOURCE_NOT_FOUND)
        except (MCPRuntimeError, ContextError, TimeoutError, ToolMCPRuntimeError) as e:
            return self._process_error(e, message, types.INTERNAL_ERROR)
        except InternalMCPError as e:
            return self._process_error(e, message, types.INTERNAL_ERROR)
        except Exception as e:
            return self._process_error(e, message, types.INTERNAL_ERROR)
        except anyio.get_cancelled_exc_class() as e:
            logger.debug("Task cancelled: %s. Message: %s", e, message)
            raise  # Cancel must be re-raised

    def _parse_message(self, message: Message) -> types.JSONRPCMessage:
        """
        Parse the incoming MCP message from the client into a JSON-RPC message.

        Args:
            message: The incoming MCP message from the client.

        Returns:
            The parsed JSON-RPC message.

        Raises:
            InvalidJSONError: If the message is not a valid JSON string.
            InvalidJSONRPCMessageError: If the message is not a valid JSON-RPC object.
            InvalidMCPMessageError: If the message is not a valid MCP message.
        """
        try:
            return types.JSONRPCMessage.model_validate_json(message)
        except ValidationError as e:
            for error in e.errors():
                error_type = error.get("type", "")
                error_message = error.get("message", "")

                if error_type in ("json_type", "json_invalid"):
                    # message cannot be parsed as JSON string
                    # json_type - message passed is not a string
                    # json_invalid - message cannot be parsed as JSON
                    raise InvalidJSONError(error_message) from e
                elif error_type == "model_type":
                    # message is not a valid JSON-RPC object
                    raise InvalidJSONRPCMessageError(error_message) from e
                elif error_type in ("missing", "literal_error") and not json_rpc.check_jsonrpc_version(message):
                    # jsonrpc field is missing or not valid JSON-RPC version
                    raise InvalidJSONRPCMessageError(error_message) from e

            # Validation errors - Datatype mismatch, missing required fields, etc.
            raise InvalidMCPMessageError(str(e)) from e

    async def _handle_rpc_msg(self, rpc_msg: types.JSONRPCMessage) -> Message | NoMessage:
        """
        Handle a JSON-RPC MCP message. The message must be a request or notification.

        Args:
            rpc_msg: The JSON-RPC MCP message to handle.

        Returns:
            The response MCP message to the client. If the message is a notification,
            NoMessage.NOTIFICATION is returned.
        """
        msg_root = rpc_msg.root

        # --- Handle request ---
        if isinstance(msg_root, types.JSONRPCRequest):
            client_request = types.ClientRequest.model_validate(json_rpc.to_dict(msg_root))

            logger.debug("Handling request %s - %s", msg_root.id, client_request)
            response = await self._handle_client_request(client_request)
            logger.debug("Successfully handled request %s - Response: %s", msg_root.id, response)

            return json_rpc.build_response_message(msg_root.id, response)

        # --- Handle notification ---
        elif isinstance(msg_root, types.JSONRPCNotification):
            # TODO: Add full support for client notification - This just implements the handler.
            client_notification = types.ClientNotification.model_validate(json_rpc.to_dict(msg_root))
            notification_id = uuid.uuid4()  # Creating an id for debugging

            logger.debug("Handling notification %s - %s", notification_id, client_notification)
            response = await self._handle_client_notification(client_notification)
            logger.debug("Successfully handled notification %s", notification_id)

            return response
        else:
            raise UnsupportedMessageTypeError("Message to MCP server must be a request or notification")

    async def _handle_client_request(self, request: types.ClientRequest) -> types.ServerResult:
        request_type = type(request.root)
        if handler := self._core.request_handlers.get(request_type):
            logger.debug("Dispatching request of type %s", request_type.__name__)
            return await handler(request.root)
        else:
            raise RequestHandlerNotFoundError(f"Method not found for request type {request_type.__name__}")

    async def _handle_client_notification(self, notification: types.ClientNotification) -> NoMessage:
        notification_type = type(notification.root)
        if handler := self._core.notification_handlers.get(notification_type):
            logger.debug("Dispatching notification of type %s", notification_type.__name__)

            try:
                # Avoiding the "fire-and-forget" pattern for notifications at the server layer.
                # This behavior should be handled at the transport layer.
                # This ensures all handlers are explicitly controlled and have a defined time to live.
                await handler(notification.root)
            except Exception:
                logger.exception("Uncaught exception in notification handler")

        else:
            logger.debug("No handler found for notification type %s", notification_type.__name__)

        return NoMessage.NOTIFICATION

    async def _initialize_handler(self, req: types.InitializeRequest) -> types.ServerResult:
        """
        Custom handler for the MCP InitializeRequest.
        It is directly hooked on initializing MiniMCP, and is an integral part of MCP client-server handshake.

        Args:
            req: The InitializeRequest to handle.

        Returns:
            The InitializeResult.
        """
        client_protocol_version = req.params.protocolVersion
        server_protocol_version = (
            client_protocol_version
            if client_protocol_version in version.SUPPORTED_PROTOCOL_VERSIONS
            else types.LATEST_PROTOCOL_VERSION
        )
        # TODO: Error handling on protocol version mismatch. Handled in HTTP transport.
        # https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle#error-handling

        init_options = self._core.create_initialization_options(
            notification_options=self._notification_options,
        )

        init_result = types.InitializeResult(
            protocolVersion=server_protocol_version,
            capabilities=init_options.capabilities,
            serverInfo=types.Implementation(
                name=init_options.server_name,
                version=init_options.server_version,
            ),
            instructions=init_options.instructions,
        )

        return types.ServerResult(init_result)

    def _process_error(
        self,
        error: BaseException,
        request_message: Message,
        error_code: int,
    ) -> Message:
        data = error.data if isinstance(error, InternalMCPError) else None

        json_rpc_message, error_message = json_rpc.build_error_message(
            error,
            request_message,
            error_code,
            data=data,
            include_stack_trace=self._include_stack_trace,
        )

        logger.error(error_message, exc_info=(type(error), error, error.__traceback__))

        return json_rpc_message
