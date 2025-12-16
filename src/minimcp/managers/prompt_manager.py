import builtins
import logging
from collections.abc import Callable
from functools import partial
from typing import Any

import pydantic_core
from mcp.server.lowlevel.server import Server
from mcp.types import AnyFunction, GetPromptResult, Prompt, PromptArgument, PromptMessage, TextContent
from typing_extensions import TypedDict, Unpack

from minimcp.exceptions import InvalidArgumentsError, MCPRuntimeError, PrimitiveError
from minimcp.utils.mcp_func import MCPFunc

logger = logging.getLogger(__name__)


class PromptDefinition(TypedDict, total=False):
    """
    Type definition for prompt parameters.

    Attributes:
        name: Optional unique identifier for the prompt. If not provided, the function name is used.
            Must be unique across all prompts in the server.
        title: Optional human-readable name for display purposes. Shows in client UIs (e.g., as slash commands).
        description: Optional human-readable description of what the prompt does. If not provided,
            the function's docstring is used.
        meta: Optional metadata dictionary for additional prompt information.
    """

    name: str | None
    title: str | None
    description: str | None
    meta: dict[str, Any] | None


class PromptManager:
    """
    PromptManager is responsible for registration and execution of MCP prompt handlers.

    The Model Context Protocol (MCP) provides a standardized way for servers to expose prompt templates
    to clients. Prompts allow servers to provide structured messages and instructions for interacting
    with language models. Clients can discover available prompts, retrieve their contents, and provide
    arguments to customize them.

    Prompts are designed to be user-controlled, exposed from servers to clients with the intention of
    the user being able to explicitly select them for use. Typically, prompts are triggered through
    user-initiated commands in the user interface, such as slash commands in chat applications.

    The PromptManager can be used as a decorator (@mcp.prompt()) or programmatically via the mcp.prompt.add(),
    mcp.prompt.list(), mcp.prompt.get() and mcp.prompt.remove() methods.

    When a prompt handler is added, its name (unique identifier) and description are automatically inferred
    from the handler function. You can override these by passing explicit parameters. The title field provides
    a human-readable name for display in client UIs. Prompt arguments are always inferred from the function
    signature. Type annotations are required in the function signature for correct argument extraction.

    Prompt messages can contain different content types (text, image, audio, embedded resources) and support
    optional annotations for metadata. Handler functions typically return strings or PromptMessage objects,
    which are automatically converted to the appropriate message format with role ("user" or "assistant").

    For more details, see: https://modelcontextprotocol.io/specification/2025-06-18/server/prompts

    Example:
        @mcp.prompt()
        def problem_solving(problem_description: str) -> str:
            return f"You are a math problem solver. Solve: {problem_description}"

        # With display title for UI (e.g., as slash command)
        @mcp.prompt(name="solver", title="💡 Problem Solver", description="Solve a math problem")
        def problem_solving(problem_description: str) -> str:
            return f"You are a math problem solver. Solve: {problem_description}"

        # Or programmatically:
        mcp.prompt.add(problem_solving, name="solver", title="Problem Solver")
    """

    _prompts: dict[str, tuple[Prompt, MCPFunc]]

    def __init__(self, core: Server):
        """
        Args:
            core: The low-level MCP Server instance to hook into.
        """
        self._prompts = {}
        self._hook_core(core)

    def _hook_core(self, core: Server) -> None:
        """Register prompt handlers with the MCP core server.

        Args:
            core: The low-level MCP Server instance to hook into.
        """
        core.list_prompts()(self._async_list)
        core.get_prompt()(self.get)
        # core.complete()(self._async_complete) # TODO: Implement completion for prompts

    def __call__(self, **kwargs: Unpack[PromptDefinition]) -> Callable[[AnyFunction], Prompt]:
        """Decorator to add/register a prompt handler at the time of handler function definition.

        Prompt name and description are automatically inferred from the handler function. You can override
        these by passing explicit parameters (name, title, description, meta) as shown in the example below.
        Prompt arguments are always inferred from the function signature. Type annotations are required
        in the function signature for proper argument extraction.

        Args:
            **kwargs: Optional prompt definition parameters (name, title, description, meta).
                Parameters are defined in the PromptDefinition class.

        Returns:
            A decorator function that adds the prompt handler.

        Example:
            @mcp.prompt(name="code_review", title="🔍 Request Code Review")
            def code_review(code: str) -> str:
                return f"Please review this code:\n{code}"
        """
        return partial(self.add, **kwargs)

    def add(self, func: AnyFunction, **kwargs: Unpack[PromptDefinition]) -> Prompt:
        """To programmatically add/register a prompt handler function.

        This is useful when the handler function is already defined and you have a function object
        that needs to be registered at runtime.

        If not provided, the prompt name (unique identifier) and description are automatically inferred
        from the function's name and docstring. The title field should be provided for better display in
        client UIs. Arguments are always automatically inferred from the function signature. Type annotations
        are required in the function signature for proper argument extraction and validation.

        Handler functions can return:
        - str: Converted to a user message with text content
        - PromptMessage: Used as-is with role ("user" or "assistant") and content
        - dict: Validated as PromptMessage
        - list/tuple: Multiple messages of any of the above types
        - Other types: JSON-serialized and converted to user messages

        Args:
            func: The prompt handler function. Can be synchronous or asynchronous. Should return
                content that can be converted to PromptMessage objects.
            **kwargs: Optional prompt definition parameters to override inferred
                values (name, title, description, meta). Parameters are defined in
                the PromptDefinition class.

        Returns:
            The registered Prompt object with unique identifier, optional title for display,
            and inferred arguments.

        Raises:
            PrimitiveError: If a prompt with the same name is already registered or if the function
                isn't properly typed.
        """

        prompt_func = MCPFunc(func, kwargs.get("name"))
        if prompt_func.name in self._prompts:
            raise PrimitiveError(f"Prompt {prompt_func.name} already registered")

        prompt = Prompt(
            name=prompt_func.name,
            title=kwargs.get("title", None),
            description=kwargs.get("description", prompt_func.doc),
            arguments=self._get_arguments(prompt_func),
            _meta=kwargs.get("meta", None),
        )

        self._prompts[prompt_func.name] = (prompt, prompt_func)
        logger.debug("Prompt %s added", prompt_func.name)

        return prompt

    def _get_arguments(self, prompt_func: MCPFunc) -> list[PromptArgument]:
        """Get the arguments for a prompt from the function signature per MCP specification.

        Extracts parameter information from the function's input schema generated by MCPFunc,
        converting them to PromptArgument objects for MCP protocol compliance. Each argument
        includes a name, optional description, and required flag.

        Arguments enable prompt customization and may be auto-completed through the MCP completion API.

        Args:
            prompt_func: The MCPFunc wrapper containing the function's input schema.

        Returns:
            A list of PromptArgument objects describing the prompt's parameters for customization.
        """
        arguments: list[PromptArgument] = []

        input_schema = prompt_func.input_schema
        if "properties" in input_schema:
            for param_name, param in input_schema["properties"].items():
                required = param_name in input_schema.get("required", [])
                arguments.append(
                    PromptArgument(
                        name=param_name,
                        description=param.get("description"),
                        required=required,
                    )
                )

        return arguments

    def remove(self, name: str) -> Prompt:
        """Remove a prompt by name.

        Args:
            name: The name of the prompt to remove.

        Returns:
            The removed Prompt object.

        Raises:
            PrimitiveError: If the prompt is not found.
        """
        if name not in self._prompts:
            # Raise INVALID_PARAMS as per MCP specification
            raise PrimitiveError(f"Unknown prompt: {name}")

        return self._prompts.pop(name)[0]

    def list(self) -> builtins.list[Prompt]:
        """List all registered prompts.

        Returns:
            A list of all registered Prompt objects.
        """
        return [prompt[0] for prompt in self._prompts.values()]

    async def _async_list(self) -> builtins.list[Prompt]:
        """Async wrapper for list().

        Returns:
            A list of all registered Prompt objects.
        """
        return self.list()

    async def get(self, name: str, args: dict[str, str] | None) -> GetPromptResult:
        """Retrieve and execute a prompt by name, as specified in the MCP prompts/get protocol.

        This method handles the MCP prompts/get request, executing the prompt handler function with
        the provided arguments. Arguments are validated against the prompt's argument definitions,
        and the result is converted to PromptMessage objects per the MCP specification.

        PromptMessages include a role ("user" or "assistant") and content, which can be text, image,
        audio, or embedded resources. All content types support optional annotations for metadata.

        Args:
            name: The unique identifier of the prompt to retrieve.
            args: Optional dictionary of arguments to pass to the prompt handler. Must include all
                required arguments as defined in the prompt. Arguments may be auto-completed through
                the completion API.

        Returns:
            GetPromptResult containing:
            - description: Human-readable description of the prompt
            - messages: List of PromptMessage objects with role and content
            - _meta: Optional metadata

        Raises:
            PrimitiveError: If the prompt is not found (maps to -32602 Invalid params per spec).
            MCPRuntimeError: If an error occurs during prompt execution or message conversion
                (maps to -32603 Internal error per spec).
        """
        if name not in self._prompts:
            # Raise INVALID_PARAMS as per MCP specification
            raise PrimitiveError(f"Unknown prompt: {name}")

        prompt, prompt_func = self._prompts[name]
        self._validate_args(prompt.arguments, args)

        try:
            result = await prompt_func.execute(args)
            messages = self._convert_result(result)
            logger.debug("Prompt %s handled with args %s", name, args)

            return GetPromptResult(
                description=prompt.description,
                messages=messages,
                _meta=prompt.meta,
            )
        except InvalidArgumentsError:
            raise
        except Exception as e:
            msg = f"Error getting prompt {name}: {e}"
            logger.exception(msg)
            raise MCPRuntimeError(msg) from e

    def _validate_args(
        self, prompt_arguments: builtins.list[PromptArgument] | None, available_args: dict[str, Any] | None
    ) -> None:
        """Check for missing required arguments per MCP specification.

        Args:
            prompt_arguments: The arguments for the prompt.
            available_args: The arguments provided by the client.

        Raises:
            InvalidArgumentsError: If the required arguments are not provided.
        """
        if prompt_arguments is None:
            return

        required_arg_names = {arg.name for arg in prompt_arguments if arg.required}
        provided_arg_names = set(available_args or {})

        missing_arg_names = required_arg_names - provided_arg_names
        if missing_arg_names:
            missing_arg_names_str = ", ".join(missing_arg_names)
            raise InvalidArgumentsError(
                f"Missing required arguments: Arguments {missing_arg_names_str} need to be provided"
            )

    def _convert_result(self, result: Any) -> builtins.list[PromptMessage]:
        """Convert prompt handler results to PromptMessage objects per MCP specification.

        PromptMessages must include a role ("user" or "assistant") and content. Per the MCP spec,
        content can be:
        - Text content (type: "text") - most common for natural language interactions
        - Image content (type: "image") - base64-encoded with MIME type
        - Audio content (type: "audio") - base64-encoded with MIME type
        - Embedded resources (type: "resource") - server-side resources with URI

        All content types support optional annotations for metadata about audience, priority,
        and modification times.

        Supports multiple return types from handler functions:
        - PromptMessage objects (used as-is with role and content)
        - Dictionaries (validated as PromptMessage)
        - Strings (converted to user messages with text content)
        - Other types (JSON-serialized and converted to user messages with text content)
        - Lists/tuples of any of the above

        Args:
            result: The return value from a prompt handler function.

        Returns:
            A list of PromptMessage objects with role and content per MCP protocol.

        Raises:
            MCPRuntimeError: If the result cannot be converted to valid messages.
        """

        if not isinstance(result, list | tuple):
            result = [result]

        try:
            messages: list[PromptMessage] = []

            for msg in result:  # type: ignore[reportUnknownVariableType]
                if isinstance(msg, PromptMessage):
                    messages.append(msg)
                elif isinstance(msg, dict):
                    # Try to validate as PromptMessage
                    messages.append(PromptMessage.model_validate(msg))
                elif isinstance(msg, str):
                    # Create a user message with text content
                    content = TextContent(type="text", text=msg)
                    messages.append(PromptMessage(role="user", content=content))
                else:
                    # Convert to JSON string and create user message
                    content_text = pydantic_core.to_json(msg, fallback=str, indent=2).decode()
                    content = TextContent(type="text", text=content_text)
                    messages.append(PromptMessage(role="user", content=content))

            return messages
        except Exception as e:
            raise MCPRuntimeError("Could not convert prompt result to message") from e
