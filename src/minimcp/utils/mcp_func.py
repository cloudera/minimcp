import functools
import inspect
from typing import Any

from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata, func_metadata
from mcp.types import AnyFunction
from pydantic import ValidationError

from minimcp.exceptions import InvalidArgumentsError, MCPFuncError


# TODO: Do performance profiling of this class, find hot spots and optimize.
# This needs to be lean and fast.
class MCPFunc:
    """
    Validates and wraps a Python function for use as an MCP handler.

    Function is valid if it satisfies the following conditions:
    - Is not a classmethod, staticmethod, or abstract method
    - Does not use *args or **kwargs (MCP requires explicit parameters)
    - Is a valid callable

    Generates schemas from function signature and return type:
    - input_schema: Function parameters (via Pydantic model)
    - output_schema: Return type (optional, for structured output)

    The execute() method can be called with a set of arguments. MCPFunc will
    validate the arguments against the function signature, call the function,
    and return the result.
    """

    func: AnyFunction
    name: str
    doc: str | None
    is_async: bool

    meta: FuncMetadata
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None

    def __init__(self, func: AnyFunction, name: str | None = None):
        """
        Args:
            func: The function to validate.
            name: The custom name to use for the function.
        """

        self._validate_func(func)

        self.func = func
        self.name = self._get_name(name)
        self.doc = inspect.getdoc(func)
        self.is_async = self._is_async_callable(func)

        self.meta = func_metadata(func)
        self.input_schema = self.meta.arg_model.model_json_schema(by_alias=True)
        self.output_schema = self.meta.output_schema

    def _validate_func(self, func: AnyFunction) -> None:
        """
        Validates a function's usability as an MCP handler function.

        Validation fails for the following reasons:
        - If the function is a classmethod - MCP cannot inject cls as the first parameter
        - If the function is a staticmethod - @staticmethod returns a descriptor object, not a callable function
        - If the function is an abstract method - Abstract methods are not directly callable
        - If the function is not a function or method
        - If the function has *args or **kwargs - MCP cannot pass variable number of arguments

        Args:
            func: The function to validate.

        Raises:
            ValueError: If the function is not a valid MCP handler function.
        """

        if isinstance(func, classmethod):
            raise MCPFuncError("Function cannot be a classmethod")

        if isinstance(func, staticmethod):
            raise MCPFuncError("Function cannot be a staticmethod")

        if getattr(func, "__isabstractmethod__", False):
            raise MCPFuncError("Function cannot be an abstract method")

        if not inspect.isroutine(func):
            raise MCPFuncError("Object passed is not a function or method")

        sig = inspect.signature(func)
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                raise MCPFuncError("Functions with *args are not supported")
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                raise MCPFuncError("Functions with **kwargs are not supported")

    def _get_name(self, name: str | None) -> str:
        """
        Infers the name of the function from the function object.

        Args:
            name: The custom name to use for the function.

        Raises:
            MCPFuncError: If the name cannot be inferred from the function and no custom name is provided.
        """

        if name:
            name = name.strip()

        if not name:
            name = str(getattr(self.func, "__name__", None))

            if not name:
                raise MCPFuncError("Name cannot be inferred from the function. Please provide a custom name.")
            elif name == "<lambda>":
                raise MCPFuncError("Lambda functions must be named. Please provide a custom name.")

        return name

    async def execute(self, args: dict[str, Any] | None = None) -> Any:
        """
        Validates and executes the function with the given arguments and returns the result.
        If the function is asynchronous, it will be awaited.

        Args:
            args: The arguments to pass to the function.

        Returns:
            The result of the function execution.

        Raises:
            InvalidArgumentsError: If the arguments are not valid.
        """

        try:
            arguments_pre_parsed = self.meta.pre_parse_json(args or {})
            arguments_parsed_model = self.meta.arg_model.model_validate(arguments_pre_parsed)
            arguments_parsed_dict = arguments_parsed_model.model_dump_one_level()
        except ValidationError as e:
            raise InvalidArgumentsError(f"Invalid arguments: {e}") from e

        if self.is_async:
            return await self.func(**arguments_parsed_dict)
        else:
            return self.func(**arguments_parsed_dict)

    def _is_async_callable(self, obj: AnyFunction) -> bool:
        """
        Determines if a function is awaitable.

        Args:
            obj: The function to determine if it is asynchronous.

        Returns:
            True if the function is asynchronous, False otherwise.
        """
        while isinstance(obj, functools.partial):
            obj = obj.func

        return inspect.iscoroutinefunction(obj) or (
            callable(obj) and inspect.iscoroutinefunction(getattr(obj, "__call__", None))
        )
