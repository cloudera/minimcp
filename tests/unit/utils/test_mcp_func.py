from typing import Any
from unittest.mock import Mock, patch

import pytest
from mcp.types import AnyFunction
from pydantic import BaseModel

from minimcp.exceptions import InvalidArgumentsError, MCPFuncError
from minimcp.utils.mcp_func import MCPFunc

pytestmark = pytest.mark.anyio


class TestMCPFuncValidation:
    """Test suite for MCPFunc validation logic."""

    def test_init_with_valid_function(self):
        """Test initialization with a valid function."""

        def valid_func(a: int, b: str) -> str:
            """A valid function."""
            return f"{a}{b}"

        mcp_func = MCPFunc(valid_func)

        assert mcp_func.func == valid_func
        assert mcp_func.name == "valid_func"
        assert mcp_func.doc == "A valid function."
        assert mcp_func.meta is not None

    def test_init_with_valid_async_function(self):
        """Test initialization with a valid async function."""

        async def valid_async_func(x: int) -> int:
            """An async function."""
            return x * 2

        mcp_func = MCPFunc(valid_async_func)

        assert mcp_func.func == valid_async_func
        assert mcp_func.name == "valid_async_func"
        assert mcp_func.doc == "An async function."
        assert mcp_func.meta is not None

    def test_init_with_custom_name(self):
        """Test initialization with a custom name."""

        def func(a: int) -> int:
            return a

        mcp_func = MCPFunc(func, name="custom_name")

        assert mcp_func.name == "custom_name"
        assert mcp_func.func == func

    def test_init_with_custom_name_with_whitespace(self):
        """Test initialization with custom name that has whitespace."""

        def func(a: int) -> int:
            return a

        mcp_func = MCPFunc(func, name="  custom_name  ")

        assert mcp_func.name == "custom_name"

    def test_reject_classmethod(self):
        """Test that classmethods are rejected."""

        # When accessing a classmethod from a class, you need to get the raw descriptor
        # from __dict__ to test isinstance(func, classmethod)
        class MyClass:
            @classmethod
            def class_method(cls, a: int) -> int:
                return a

        # Access the classmethod descriptor directly from __dict__
        class_method_descriptor = MyClass.__dict__["class_method"]

        with pytest.raises(MCPFuncError, match="Function cannot be a classmethod"):
            MCPFunc(class_method_descriptor)

    def test_reject_staticmethod(self):
        """Test that staticmethods are rejected."""

        # When accessing a staticmethod from a class, you need to get the raw descriptor
        # from __dict__ to test isinstance(func, staticmethod)
        class MyClass:
            @staticmethod
            def static_method(a: int) -> int:
                return a

        # Access the staticmethod descriptor directly from __dict__
        static_method_descriptor = MyClass.__dict__["static_method"]

        with pytest.raises(MCPFuncError, match="Function cannot be a staticmethod"):
            MCPFunc(static_method_descriptor)

    def test_reject_abstract_method(self):
        """Test that abstract methods are rejected."""

        # Create a class that simulates an abstract method
        # (we can't directly test with @abstractmethod because it's checked at instantiation)
        class FakeAbstractMethod:
            __isabstractmethod__ = True

            def __call__(self, a: int) -> int:
                return a

        # Test with the fake abstract method
        fake_abstract = FakeAbstractMethod()

        with pytest.raises(MCPFuncError, match="Function cannot be an abstract method"):
            MCPFunc(fake_abstract)  # type: ignore

    def test_reject_non_function(self):
        """Test that non-functions are rejected."""

        not_a_function = "this is a string"

        with pytest.raises(MCPFuncError, match="Object passed is not a function or method"):
            MCPFunc(not_a_function)  # type: ignore

    def test_reject_function_with_var_positional(self):
        """Test that functions with *args are rejected."""

        def func_with_args(a: int, *args: int) -> int:
            return a + sum(args)

        with pytest.raises(MCPFuncError, match="Functions with \\*args are not supported"):
            MCPFunc(func_with_args)

    def test_reject_function_with_var_keyword(self):
        """Test that functions with **kwargs are rejected."""

        def func_with_kwargs(a: int, **kwargs: Any) -> int:
            return a

        with pytest.raises(MCPFuncError, match="Functions with \\*\\*kwargs are not supported"):
            MCPFunc(func_with_kwargs)

    def test_reject_function_with_both_var_args_and_kwargs(self):
        """Test that functions with both *args and **kwargs are rejected."""

        def func_with_both(a: int, *args: int, **kwargs: Any) -> int:
            return a

        # Should fail on *args first
        with pytest.raises(MCPFuncError, match="Functions with \\*args are not supported"):
            MCPFunc(func_with_both)

    def test_accept_method(self):
        """Test that instance methods are accepted."""

        class MyClass:
            def instance_method(self, a: int) -> int:
                return a * 2

        instance = MyClass()
        mcp_func = MCPFunc(instance.instance_method)

        assert mcp_func.name == "instance_method"
        assert mcp_func.func == instance.instance_method


class TestMCPFuncNameInference:
    """Test suite for MCPFunc name inference logic."""

    def test_name_inferred_from_function(self):
        """Test that name is correctly inferred from function.__name__."""

        def my_function(a: int) -> int:
            return a

        mcp_func = MCPFunc(my_function)

        assert mcp_func.name == "my_function"

    def test_custom_name_overrides_function_name(self):
        """Test that custom name overrides function.__name__."""

        def original_name(a: int) -> int:
            return a

        mcp_func = MCPFunc(original_name, name="custom_override")

        assert mcp_func.name == "custom_override"

    def test_empty_custom_name_falls_back_to_function_name(self):
        """Test that empty string custom name falls back to function name."""

        def fallback_func(a: int) -> int:
            return a

        mcp_func = MCPFunc(fallback_func, name="")

        assert mcp_func.name == "fallback_func"

    def test_whitespace_only_custom_name_falls_back(self):
        """Test that whitespace-only custom name falls back to function name."""

        def whitespace_func(a: int) -> int:
            return a

        mcp_func = MCPFunc(whitespace_func, name="   ")

        assert mcp_func.name == "whitespace_func"

    def test_reject_lambda_without_custom_name(self):
        """Test that lambda functions without custom name are rejected."""

        lambda_func: AnyFunction = lambda a: a  # noqa: E731  # type: ignore

        with pytest.raises(MCPFuncError, match="Lambda functions must be named"):
            MCPFunc(lambda_func)

    def test_accept_lambda_with_custom_name(self):
        """Test that lambda functions with custom name are accepted."""

        lambda_func: AnyFunction = lambda a: a  # noqa: E731  # type: ignore

        mcp_func = MCPFunc(lambda_func, name="named_lambda")

        assert mcp_func.name == "named_lambda"

    def test_function_without_name_attribute_rejects(self):
        """Test handling of callable objects that are not functions."""

        class CallableWithoutName:
            def __call__(self, a: int) -> int:
                return a

        callable_obj = CallableWithoutName()

        # Callable objects fail validation because they're not routines
        with pytest.raises(MCPFuncError, match="Object passed is not a function or method"):
            MCPFunc(callable_obj)  # type: ignore


class TestMCPFuncSchemas:
    """Test suite for MCPFunc schema generation."""

    def test_input_schema_simple_types(self):
        """Test input schema generation with simple types."""

        def simple_func(a: int, b: str, c: float) -> None:
            pass

        mcp_func = MCPFunc(simple_func)
        schema = mcp_func.input_schema

        assert "properties" in schema
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]
        assert "c" in schema["properties"]

    def test_input_schema_cached(self):
        """Test that input_schema is cached using cached_property."""

        def func(a: int) -> int:
            return a

        mcp_func = MCPFunc(func)

        # Get schema twice
        schema1 = mcp_func.input_schema
        schema2 = mcp_func.input_schema

        # Should be the same object (cached)
        assert schema1 is schema2

    def test_output_schema(self):
        """Test output schema generation."""

        def func_with_output(a: int) -> int:
            return a

        mcp_func = MCPFunc(func_with_output)
        output_schema = mcp_func.output_schema

        # Output schema may or may not be None depending on implementation
        # Just verify it doesn't raise an error
        assert output_schema is None or isinstance(output_schema, dict)

    def test_output_schema_cached(self):
        """Test that output_schema is cached using cached_property."""

        def func(a: int) -> int:
            return a

        mcp_func = MCPFunc(func)

        # Get schema twice
        schema1 = mcp_func.output_schema
        schema2 = mcp_func.output_schema

        # Should be the same object (cached)
        assert schema1 is schema2

    def test_input_schema_with_optional_parameters(self):
        """Test input schema with optional parameters."""

        def func_with_optional(a: int, b: str = "default") -> None:
            pass

        mcp_func = MCPFunc(func_with_optional)
        schema = mcp_func.input_schema

        assert "properties" in schema
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]

    def test_input_schema_with_pydantic_model(self):
        """Test input schema with Pydantic model as parameter."""

        class InputModel(BaseModel):
            field1: str
            field2: int

        def func_with_model(data: InputModel) -> None:
            pass

        mcp_func = MCPFunc(func_with_model)
        schema = mcp_func.input_schema

        assert "properties" in schema
        assert "data" in schema["properties"]


class TestMCPFuncExecution:
    """Test suite for MCPFunc execution logic."""

    async def test_execute_sync_function(self):
        """Test execution of a synchronous function."""

        def add_func(a: int, b: int) -> int:
            return a + b

        mcp_func = MCPFunc(add_func)
        result = await mcp_func.execute({"a": 5, "b": 3})

        assert result == 8

    async def test_execute_async_function(self):
        """Test execution of an asynchronous function."""

        async def async_add(a: int, b: int) -> int:
            return a + b

        mcp_func = MCPFunc(async_add)
        result = await mcp_func.execute({"a": 10, "b": 20})

        assert result == 30

    async def test_execute_validates_arguments(self):
        """Test that execute validates arguments against the schema."""

        def typed_func(a: int, b: str) -> str:
            return f"{a}{b}"

        mcp_func = MCPFunc(typed_func)

        # Valid arguments
        result = await mcp_func.execute({"a": 42, "b": "hello"})
        assert result == "42hello"

        # Invalid arguments should raise InvalidArgumentsError
        with pytest.raises(InvalidArgumentsError, match="Input should be a valid integer"):
            await mcp_func.execute({"a": "not_an_int", "b": "hello"})

    async def test_execute_missing_required_argument(self):
        """Test that execute raises error for missing required arguments."""

        def func(a: int, b: str) -> str:
            return f"{a}{b}"

        mcp_func = MCPFunc(func)

        with pytest.raises(InvalidArgumentsError, match="Field required"):
            await mcp_func.execute({"a": 42})  # Missing 'b'

    async def test_execute_with_optional_arguments(self):
        """Test execution with optional arguments."""

        def func_with_default(a: int, b: str = "default") -> str:
            return f"{a}{b}"

        mcp_func = MCPFunc(func_with_default)

        # With optional argument
        result1 = await mcp_func.execute({"a": 1, "b": "custom"})
        assert result1 == "1custom"

        # Without optional argument (should use default)
        result2 = await mcp_func.execute({"a": 2})
        assert result2 == "2default"

    async def test_execute_extra_arguments_ignored_or_rejected(self):
        """Test behavior with extra arguments not in schema."""

        def simple_func(a: int) -> int:
            return a * 2

        mcp_func = MCPFunc(simple_func)

        # Extra arguments are ignored by pydantic (depends on model configuration)
        # The function should execute successfully, just ignoring extra args
        result = await mcp_func.execute({"a": 5, "extra": "not_expected"})
        assert result == 10

    async def test_execute_returns_function_result(self):
        """Test that execute returns the actual function result."""

        def multiply(a: int, b: int) -> int:
            return a * b

        mcp_func = MCPFunc(multiply)
        result = await mcp_func.execute({"a": 7, "b": 6})

        assert result == 42

    async def test_execute_complex_return_type(self):
        """Test execution with complex return types."""

        def complex_func(a: int) -> dict[str, Any]:
            return {"result": a * 2, "status": "success"}

        mcp_func = MCPFunc(complex_func)
        result = await mcp_func.execute({"a": 10})

        assert result == {"result": 20, "status": "success"}

    async def test_execute_none_return(self):
        """Test execution of function that returns None."""

        def void_func(a: int) -> None:
            pass

        mcp_func = MCPFunc(void_func)
        result = await mcp_func.execute({"a": 5})

        assert result is None

    async def test_execute_async_function_with_await(self):
        """Test that async functions are properly awaited."""

        call_count = 0

        async def async_counter(increment: int) -> int:
            nonlocal call_count
            call_count += increment
            return call_count

        mcp_func = MCPFunc(async_counter)

        result1 = await mcp_func.execute({"increment": 5})
        assert result1 == 5

        result2 = await mcp_func.execute({"increment": 3})
        assert result2 == 8

    async def test_execute_function_with_side_effects(self):
        """Test execution of functions with side effects."""

        side_effect_list: list[int] = []

        def side_effect_func(value: int) -> int:
            side_effect_list.append(value)
            return value * 2

        mcp_func = MCPFunc(side_effect_func)
        result = await mcp_func.execute({"value": 10})

        assert result == 20
        assert side_effect_list == [10]

    async def test_execute_with_type_coercion(self):
        """Test that pydantic validates types strictly."""

        def string_func(value: str) -> str:
            return f"Value: {value}"

        mcp_func = MCPFunc(string_func)

        with pytest.raises(InvalidArgumentsError, match="Input should be a valid string"):
            await mcp_func.execute({"value": 42})

        # But string should work fine
        result = await mcp_func.execute({"value": "42"})
        assert result == "Value: 42"


class TestMCPFuncEdgeCases:
    """Test suite for edge cases and error scenarios."""

    def test_function_with_no_parameters(self):
        """Test function with no parameters."""

        def no_params() -> str:
            return "no params"

        mcp_func = MCPFunc(no_params)

        assert mcp_func.name == "no_params"
        assert mcp_func.func == no_params

    async def test_execute_no_params_function(self):
        """Test executing a function with no parameters."""

        def no_params() -> str:
            return "success"

        mcp_func = MCPFunc(no_params)
        result = await mcp_func.execute({})

        assert result == "success"

    def test_function_with_complex_annotations(self):
        """Test function with complex type annotations."""

        def complex_annotations(
            a: list[int],
            b: dict[str, Any],
            c: tuple[int, str],
        ) -> list[dict[str, Any]]:
            return [{"a": a, "b": b, "c": c}]

        mcp_func = MCPFunc(complex_annotations)

        assert mcp_func.name == "complex_annotations"
        assert mcp_func.meta is not None

    def test_docstring_extraction(self):
        """Test that docstrings are properly extracted."""

        def documented_func(a: int) -> int:
            """This is a comprehensive docstring.

            It has multiple lines.
            """
            return a

        mcp_func = MCPFunc(documented_func)

        assert mcp_func.doc is not None
        assert "comprehensive docstring" in mcp_func.doc

    def test_function_without_docstring(self):
        """Test function without a docstring."""

        def undocumented_func(a: int) -> int:
            return a

        mcp_func = MCPFunc(undocumented_func)

        assert mcp_func.doc is None

    async def test_execute_propagates_function_exceptions(self):
        """Test that exceptions from the function are propagated."""

        def error_func(a: int) -> int:
            raise RuntimeError("Intentional error")

        mcp_func = MCPFunc(error_func)

        with pytest.raises(RuntimeError, match="Intentional error"):
            await mcp_func.execute({"a": 5})

    async def test_execute_async_function_exception(self):
        """Test that exceptions from async functions are propagated."""

        async def async_error_func(a: int) -> int:
            raise MCPFuncError("Async error")

        mcp_func = MCPFunc(async_error_func)

        with pytest.raises(MCPFuncError, match="Async error"):
            await mcp_func.execute({"a": 5})

    def test_metadata_is_created_on_init(self):
        """Test that func_metadata is called during initialization."""

        def test_func(a: int) -> int:
            return a

        with patch("minimcp.utils.mcp_func.func_metadata") as mock_metadata:
            mock_metadata.return_value = Mock()

            mcp_func = MCPFunc(test_func)

            mock_metadata.assert_called_once_with(test_func)
            assert mcp_func.meta == mock_metadata.return_value


class TestMCPFuncIntegration:
    """Integration tests for MCPFunc with real-world scenarios."""

    async def test_calculator_functions(self):
        """Test calculator-like functions."""

        def add(a: float, b: float) -> float:
            """Add two numbers."""
            return a + b

        def multiply(a: float, b: float) -> float:
            """Multiply two numbers."""
            return a * b

        add_func = MCPFunc(add)
        mult_func = MCPFunc(multiply)

        assert await add_func.execute({"a": 2.5, "b": 3.5}) == 6.0
        assert await mult_func.execute({"a": 2.0, "b": 5.0}) == 10.0

    async def test_string_manipulation_functions(self):
        """Test string manipulation functions."""

        def concat(a: str, b: str, separator: str = " ") -> str:
            """Concatenate strings with separator."""
            return f"{a}{separator}{b}"

        def uppercase(text: str) -> str:
            """Convert to uppercase."""
            return text.upper()

        concat_func = MCPFunc(concat)
        upper_func = MCPFunc(uppercase)

        assert await concat_func.execute({"a": "hello", "b": "world"}) == "hello world"
        assert await concat_func.execute({"a": "hello", "b": "world", "separator": "-"}) == "hello-world"
        assert await upper_func.execute({"text": "hello"}) == "HELLO"

    async def test_async_data_processing(self):
        """Test async data processing functions."""

        async def fetch_and_process(url: str, timeout: int = 30) -> dict[str, Any]:
            """Simulate async data fetching and processing."""
            # Simulate async operation
            return {"url": url, "timeout": timeout, "status": "success"}

        fetch_func = MCPFunc(fetch_and_process)
        result = await fetch_func.execute({"url": "https://example.com"})

        assert result["url"] == "https://example.com"
        assert result["timeout"] == 30
        assert result["status"] == "success"

    async def test_pydantic_model_validation(self):
        """Test with Pydantic models as parameters."""

        class User(BaseModel):
            name: str
            age: int
            email: str

        def process_user(user: User) -> str:
            """Process user data."""
            return f"{user.name} ({user.age}) - {user.email}"

        process_func = MCPFunc(process_user)

        result = await process_func.execute({"user": {"name": "John Doe", "age": 30, "email": "john@example.com"}})

        assert result == "John Doe (30) - john@example.com"

    async def test_multiple_executions_same_function(self):
        """Test executing the same MCPFunc multiple times."""

        counter = 0

        def increment(amount: int) -> int:
            """Increment counter."""
            nonlocal counter
            counter += amount
            return counter

        inc_func = MCPFunc(increment)

        result1 = await inc_func.execute({"amount": 5})
        assert result1 == 5

        result2 = await inc_func.execute({"amount": 3})
        assert result2 == 8

        result3 = await inc_func.execute({"amount": 2})
        assert result3 == 10

    def test_method_binding_preserved(self):
        """Test that method binding is preserved."""

        class Calculator:
            def __init__(self):
                self.history: list[int] = []

            def calculate(self, a: int, b: int) -> int:
                result = a + b
                self.history.append(result)
                return result

        calc = Calculator()
        calc_func = MCPFunc(calc.calculate)

        assert calc_func.name == "calculate"

    async def test_method_execution_with_state(self):
        """Test executing methods that modify instance state."""

        class Counter:
            def __init__(self):
                self.count = 0

            def increment(self, amount: int = 1) -> int:
                self.count += amount
                return self.count

        counter = Counter()
        inc_func = MCPFunc(counter.increment)

        result1 = await inc_func.execute({"amount": 5})
        assert result1 == 5
        assert counter.count == 5

        result2 = await inc_func.execute({"amount": 3})
        assert result2 == 8
        assert counter.count == 8


class TestMCPFuncMemoryAndPerformance:
    """Test suite for memory and performance characteristics."""

    def test_multiple_instances_independent(self):
        """Test that multiple MCPFunc instances are independent."""

        def func1(a: int) -> int:
            return a

        def func2(b: str) -> str:
            return b

        mcp_func1 = MCPFunc(func1)
        mcp_func2 = MCPFunc(func2)

        assert mcp_func1.name == "func1"
        assert mcp_func2.name == "func2"
        assert mcp_func1.func is not mcp_func2.func
        assert mcp_func1.meta is not mcp_func2.meta

    def test_infer_name_with_lambda(self):
        """Test that _infer_name raises error for lambda functions."""
        lambda_func: AnyFunction = lambda x: x  # noqa: E731  # type: ignore[assignment]

        with pytest.raises(MCPFuncError, match="Lambda functions must be named"):
            MCPFunc(lambda_func)
