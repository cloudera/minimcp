from typing import Any
from unittest.mock import Mock

import anyio
import mcp.types as types
import pytest
from mcp.server.lowlevel.server import Server
from pydantic import Field

from minimcp.exceptions import InvalidArgumentsError, MCPFuncError, MCPRuntimeError, PrimitiveError
from minimcp.managers.prompt_manager import PromptDefinition, PromptManager
from minimcp.utils.mcp_func import MCPFunc

pytestmark = pytest.mark.anyio


class TestPromptManager:
    """Test suite for PromptManager class."""

    @pytest.fixture
    def mock_core(self) -> Mock:
        """Create a mock Server for testing."""
        core = Mock(spec=Server)
        core.list_prompts = Mock(return_value=Mock())
        core.get_prompt = Mock(return_value=Mock())
        return core

    @pytest.fixture
    def prompt_manager(self, mock_core: Mock) -> PromptManager:
        """Create a PromptManager instance with mocked core."""
        return PromptManager(mock_core)

    def test_init_hooks_core_methods(self, mock_core: Mock):
        """Test that PromptManager properly hooks into Server methods."""
        prompt_manager = PromptManager(mock_core)

        # Verify that core methods were called to register handlers
        mock_core.list_prompts.assert_called_once()
        mock_core.get_prompt.assert_called_once()

        # Verify internal state
        assert prompt_manager._prompts == {}

    def test_add_prompt_basic_function(self, prompt_manager: PromptManager):
        """Test adding a basic function as a prompt."""

        def sample_prompt(topic: str) -> str:
            """A sample prompt for testing."""
            return f"Tell me about {topic}"

        result = prompt_manager.add(sample_prompt)

        # Verify the returned prompt
        assert isinstance(result, types.Prompt)
        assert result.name == "sample_prompt"
        assert result.description == "A sample prompt for testing."
        assert result.arguments is not None
        assert len(result.arguments) == 1
        assert result.arguments[0].name == "topic"
        assert result.arguments[0].required is True
        assert result.title is None
        assert result.meta is None

        # Verify internal state
        assert "sample_prompt" in prompt_manager._prompts
        prompt, _ = prompt_manager._prompts["sample_prompt"]
        assert prompt == result

    def test_add_prompt_with_custom_options(self, prompt_manager: PromptManager):
        """Test adding a prompt with custom name, title, description, and metadata."""

        def basic_func(query: str) -> str:
            return f"Search for: {query}"

        custom_meta = {"version": "1.0", "category": "search"}

        result = prompt_manager.add(
            basic_func,
            name="custom_search",
            title="Custom Search Prompt",
            description="Custom description for search",
            meta=custom_meta,
        )

        assert result.name == "custom_search"
        assert result.title == "Custom Search Prompt"
        assert result.description == "Custom description for search"
        assert result.meta == custom_meta

        # Verify it's stored with custom name
        assert "custom_search" in prompt_manager._prompts
        assert "basic_func" not in prompt_manager._prompts

    def test_add_prompt_without_docstring(self, prompt_manager: PromptManager):
        """Test adding a prompt without docstring uses None as description."""

        def no_doc_prompt(text: str) -> str:
            return text

        result = prompt_manager.add(no_doc_prompt)
        assert result.description is None

    def test_add_async_prompt(self, prompt_manager: PromptManager):
        """Test adding an async function as a prompt."""

        async def async_prompt(delay: float, message: str) -> str:
            """An async prompt."""
            await anyio.sleep(delay)
            return f"Delayed message: {message}"

        result = prompt_manager.add(async_prompt)

        assert result.name == "async_prompt"
        assert result.description == "An async prompt."
        assert "async_prompt" in prompt_manager._prompts

    def test_add_prompt_with_optional_parameters(self, prompt_manager: PromptManager):
        """Test adding a prompt with optional parameters."""

        def prompt_with_defaults(required_param: str, optional_param: str = "default") -> str:
            """A prompt with optional parameters."""
            return f"{required_param} - {optional_param}"

        result = prompt_manager.add(prompt_with_defaults)

        assert result.arguments is not None
        assert len(result.arguments) == 2

        # Find arguments by name
        required_arg = next(arg for arg in result.arguments if arg.name == "required_param")
        optional_arg = next(arg for arg in result.arguments if arg.name == "optional_param")

        assert required_arg.required is True
        assert optional_arg.required is False

    def test_add_prompt_with_parameter_descriptions(self, prompt_manager: PromptManager):
        """Test that parameter descriptions are extracted from schema."""
        from typing import Annotated

        from pydantic import Field

        def prompt_with_descriptions(
            topic: Annotated[str, Field(description="The topic to write about")],
            style: Annotated[str, Field(description="Writing style to use")] = "formal",
        ) -> str:
            """A prompt with parameter descriptions."""
            return f"Write about {topic} in {style} style"

        result = prompt_manager.add(prompt_with_descriptions)

        assert result.arguments is not None
        assert len(result.arguments) == 2

        # Verify descriptions are captured
        topic_arg = next(arg for arg in result.arguments if arg.name == "topic")
        style_arg = next(arg for arg in result.arguments if arg.name == "style")

        assert topic_arg.description == "The topic to write about"
        assert topic_arg.required is True
        assert style_arg.description == "Writing style to use"
        assert style_arg.required is False

    def test_add_prompt_with_complex_parameter_types(self, prompt_manager: PromptManager):
        """Test prompts with complex parameter types like lists, dicts, Pydantic models."""
        from pydantic import BaseModel

        class PromptConfig(BaseModel):
            temperature: float
            max_tokens: int

        def advanced_prompt(topics: list[str], config: PromptConfig, metadata: dict[str, str] | None = None) -> str:
            """An advanced prompt with complex types."""
            return f"Topics: {topics}, Config: {config}"

        result = prompt_manager.add(advanced_prompt)

        assert result.name == "advanced_prompt"
        assert result.arguments is not None
        assert len(result.arguments) == 3

        # Verify all parameters are present
        param_names = {arg.name for arg in result.arguments}
        assert param_names == {"topics", "config", "metadata"}

        # Verify required vs optional
        topics_arg = next(arg for arg in result.arguments if arg.name == "topics")
        config_arg = next(arg for arg in result.arguments if arg.name == "config")
        metadata_arg = next(arg for arg in result.arguments if arg.name == "metadata")

        assert topics_arg.required is True
        assert config_arg.required is True
        assert metadata_arg.required is False

    def test_add_duplicate_prompt_raises_error(self, prompt_manager: PromptManager):
        """Test that adding a prompt with duplicate name raises PrimitiveError."""

        def prompt1(x: str) -> str:
            return x

        def prompt2(y: str) -> str:
            return y

        # Add first prompt
        prompt_manager.add(prompt1, name="duplicate_name")

        # Adding second prompt with same name should raise error
        with pytest.raises(PrimitiveError, match="Prompt duplicate_name already registered"):
            prompt_manager.add(prompt2, name="duplicate_name")

    def test_add_again_prompt_raises_error(self, prompt_manager: PromptManager):
        """Test that adding a prompt again raises PrimitiveError."""

        def prompt1(x: str) -> str:
            return x

        # Add prompt
        prompt_manager.add(prompt1)

        # Adding prompt again should raise error
        with pytest.raises(PrimitiveError, match="Prompt prompt1 already registered"):
            prompt_manager.add(prompt1)

    def test_add_lambda_without_name_raises_error(self, prompt_manager: PromptManager):
        """Test that lambda functions without custom name are rejected by MCPFunc."""
        lambda_prompt: Any = lambda x: f"Prompt: {x}"  # noqa: E731  # type: ignore[misc]

        with pytest.raises(MCPFuncError, match="Lambda functions must be named"):
            prompt_manager.add(lambda_prompt)  # type: ignore[arg-type]

    def test_add_lambda_with_custom_name_succeeds(self, prompt_manager: PromptManager):
        """Test that lambda functions with custom name work."""
        lambda_prompt: Any = lambda topic: f"Tell me about {topic}"  # noqa: E731  # type: ignore[misc]

        result = prompt_manager.add(lambda_prompt, name="custom_lambda")  # type: ignore[arg-type]
        assert result.name == "custom_lambda"
        assert "custom_lambda" in prompt_manager._prompts

    def test_add_function_with_var_args_raises_error(self, prompt_manager: PromptManager):
        """Test that functions with *args are rejected by MCPFunc."""

        def prompt_with_args(topic: str, *args: str) -> str:
            return f"Topic: {topic}"

        with pytest.raises(MCPFuncError, match="Functions with \\*args are not supported"):
            prompt_manager.add(prompt_with_args)

    def test_add_function_with_kwargs_raises_error(self, prompt_manager: PromptManager):
        """Test that functions with **kwargs are rejected by MCPFunc."""

        def prompt_with_kwargs(topic: str, **kwargs: Any) -> str:
            return f"Topic: {topic}"

        with pytest.raises(MCPFuncError, match="Functions with \\*\\*kwargs are not supported"):
            prompt_manager.add(prompt_with_kwargs)

    def test_add_bound_method_as_prompt(self, prompt_manager: PromptManager):
        """Test that bound instance methods can be added as prompts."""

        class PromptGenerator:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def generate(self, topic: str) -> str:
                """Generate a prompt with prefix."""
                return f"{self.prefix}: {topic}"

        generator = PromptGenerator("Question")
        result = prompt_manager.add(generator.generate)

        assert result.name == "generate"
        assert result.description == "Generate a prompt with prefix."
        assert "generate" in prompt_manager._prompts

    def test_add_prompt_with_no_parameters(self, prompt_manager: PromptManager):
        """Test adding a prompt that requires no parameters."""

        def static_prompt() -> str:
            """A static prompt with no parameters."""
            return "Write a creative story"

        result = prompt_manager.add(static_prompt)

        assert result.name == "static_prompt"
        assert result.arguments is not None
        assert len(result.arguments) == 0

    def test_remove_existing_prompt(self, prompt_manager: PromptManager):
        """Test removing an existing prompt."""

        def test_prompt(x: str) -> str:
            return x

        # Add prompt first
        added_prompt = prompt_manager.add(test_prompt)
        assert "test_prompt" in prompt_manager._prompts

        # Remove the prompt
        removed_prompt = prompt_manager.remove("test_prompt")

        assert removed_prompt == added_prompt
        assert "test_prompt" not in prompt_manager._prompts

    def test_remove_nonexistent_prompt_raises_error(self, prompt_manager: PromptManager):
        """Test that removing a non-existent prompt raises PrimitiveError."""
        with pytest.raises(PrimitiveError, match="Unknown prompt: nonexistent"):
            prompt_manager.remove("nonexistent")

    async def test_list_prompts_empty(self, prompt_manager: PromptManager):
        """Test listing prompts when no prompts are registered."""
        result = prompt_manager.list()
        assert result == []

        # Test async version
        async_result = await prompt_manager._async_list()
        assert async_result == []

    async def test_list_prompts_with_multiple_prompts(self, prompt_manager: PromptManager):
        """Test listing prompts when multiple prompts are registered."""

        def prompt1(x: str) -> str:
            return x

        def prompt2(y: str) -> str:
            return y

        added_prompt1 = prompt_manager.add(prompt1)
        added_prompt2 = prompt_manager.add(prompt2)

        result = prompt_manager.list()

        assert len(result) == 2
        assert added_prompt1 in result
        assert added_prompt2 in result

        # Test async version
        async_result = await prompt_manager._async_list()
        assert len(async_result) == 2
        assert added_prompt1 in async_result
        assert added_prompt2 in async_result

    async def test_get_prompt_sync_function(self, prompt_manager: PromptManager):
        """Test getting a synchronous prompt."""

        def greeting_prompt(name: str, greeting: str = "Hello") -> str:
            """Generate a greeting message."""
            return f"{greeting}, {name}!"

        prompt_manager.add(greeting_prompt)

        result = await prompt_manager.get("greeting_prompt", {"name": "Alice"})

        assert isinstance(result, types.GetPromptResult)
        assert result.description == "Generate a greeting message."
        assert len(result.messages) == 1
        assert isinstance(result.messages[0], types.PromptMessage)
        assert result.messages[0].role == "user"
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Hello, Alice!"

    async def test_get_prompt_async_function(self, prompt_manager: PromptManager):
        """Test getting an asynchronous prompt."""

        async def async_greeting_prompt(name: str) -> str:
            """Async generate a greeting message."""
            await anyio.sleep(0.01)  # Small delay to make it actually async
            return f"Hello, {name}!"

        prompt_manager.add(async_greeting_prompt)

        result = await prompt_manager.get("async_greeting_prompt", {"name": "Bob"})

        assert isinstance(result, types.GetPromptResult)
        assert result.description == "Async generate a greeting message."
        assert len(result.messages) == 1
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Hello, Bob!"

    async def test_get_prompt_with_all_arguments(self, prompt_manager: PromptManager):
        """Test getting a prompt with all arguments provided."""

        def detailed_prompt(topic: str, style: str = "formal", length: str = "short") -> str:
            """Generate a detailed prompt."""
            return f"Write a {length} {style} piece about {topic}"

        prompt_manager.add(detailed_prompt)

        result = await prompt_manager.get("detailed_prompt", {"topic": "AI", "style": "casual", "length": "long"})

        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Write a long casual piece about AI"

    async def test_get_nonexistent_prompt_raises_error(self, prompt_manager: PromptManager):
        """Test that getting a non-existent prompt raises PrimitiveError."""
        with pytest.raises(PrimitiveError, match="Unknown prompt: nonexistent"):
            await prompt_manager.get("nonexistent", {})

    async def test_get_prompt_missing_required_arguments(self, prompt_manager: PromptManager):
        """Test that getting a prompt with missing required arguments raises PrimitiveError."""

        def strict_prompt(required_param: str, optional_param: str = "default") -> str:
            """A prompt with required parameters."""
            return f"{required_param} - {optional_param}"

        prompt_manager.add(strict_prompt)

        with pytest.raises(InvalidArgumentsError, match="Missing required arguments"):
            await prompt_manager.get("strict_prompt", {})

        with pytest.raises(InvalidArgumentsError, match="Missing required arguments"):
            await prompt_manager.get("strict_prompt", {"optional_param": "value"})

    async def test_get_prompt_with_type_validation(self, prompt_manager: PromptManager):
        """Test that argument types are validated during execution."""

        def typed_prompt(count: int, message: str) -> str:
            """A prompt with strict types."""
            return f"Message {count}: {message}"

        prompt_manager.add(typed_prompt)

        # Valid types should work
        result = await prompt_manager.get("typed_prompt", {"count": 5, "message": "hello"})  # type: ignore[arg-type]
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Message 5: hello"

        # String numbers should be coerced to int by pydantic
        result2 = await prompt_manager.get("typed_prompt", {"count": "10", "message": "world"})
        assert isinstance(result2.messages[0].content, types.TextContent)
        assert result2.messages[0].content.text == "Message 10: world"

        with pytest.raises(InvalidArgumentsError, match="Input should be a valid integer"):
            await prompt_manager.get("typed_prompt", {"count": "not_a_number", "message": "hello"})

    async def test_get_prompt_with_no_parameters(self, prompt_manager: PromptManager):
        """Test prompts that require no parameters."""

        def static_prompt() -> str:
            """A static prompt with no parameters."""
            return "Write a creative story"

        prompt_manager.add(static_prompt)

        # Test with None
        result = await prompt_manager.get("static_prompt", None)
        assert len(result.messages) == 1
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Write a creative story"

        # Also test with empty dict
        result2 = await prompt_manager.get("static_prompt", {})
        assert len(result2.messages) == 1
        assert isinstance(result2.messages[0].content, types.TextContent)
        assert result2.messages[0].content.text == "Write a creative story"

    async def test_get_prompt_with_complex_arguments(self, prompt_manager: PromptManager):
        """Test getting a prompt with complex argument types."""
        from pydantic import BaseModel

        class GenerationConfig(BaseModel):
            temperature: float
            max_length: int

        def complex_prompt(topics: list[str], config: GenerationConfig) -> str:
            """A prompt with complex arguments."""
            return f"Generate text about {', '.join(topics)} with temp={config.temperature}"

        prompt_manager.add(complex_prompt)

        result = await prompt_manager.get(
            "complex_prompt",
            {"topics": ["AI", "ML"], "config": {"temperature": 0.7, "max_length": 100}},  # type: ignore[arg-type]
        )

        assert isinstance(result.messages[0].content, types.TextContent)
        assert "AI, ML" in result.messages[0].content.text
        assert "temp=0.7" in result.messages[0].content.text

    async def test_get_bound_method_prompt(self, prompt_manager: PromptManager):
        """Test getting a prompt that is a bound method."""

        class PromptGenerator:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def generate(self, topic: str) -> str:
                """Generate a prompt with prefix."""
                return f"{self.prefix}: Tell me about {topic}"

        generator = PromptGenerator("Question")
        prompt_manager.add(generator.generate)

        result = await prompt_manager.get("generate", {"topic": "Python"})

        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Question: Tell me about Python"

    async def test_get_prompt_returns_prompt_message_list(self, prompt_manager: PromptManager):
        """Test that prompt function returning PromptMessage list works correctly."""

        def multi_message_prompt(topic: str) -> list[types.PromptMessage]:
            """Generate multiple messages."""
            return [
                types.PromptMessage(
                    role="assistant", content=types.TextContent(type="text", text="I'm ready to help you.")
                ),
                types.PromptMessage(role="user", content=types.TextContent(type="text", text=f"Tell me about {topic}")),
            ]

        prompt_manager.add(multi_message_prompt)

        result = await prompt_manager.get("multi_message_prompt", {"topic": "Python"})

        assert len(result.messages) == 2
        assert result.messages[0].role == "assistant"
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "I'm ready to help you."
        assert result.messages[1].role == "user"
        assert isinstance(result.messages[1].content, types.TextContent)
        assert result.messages[1].content.text == "Tell me about Python"

    async def test_get_prompt_returns_dict_messages(self, prompt_manager: PromptManager):
        """Test that prompt function returning dict messages works correctly."""

        def dict_message_prompt(question: str) -> list[dict[str, Any]]:
            """Generate messages as dicts."""
            return [{"role": "user", "content": {"type": "text", "text": question}}]

        prompt_manager.add(dict_message_prompt)

        result = await prompt_manager.get("dict_message_prompt", {"question": "What is AI?"})

        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "What is AI?"

    async def test_get_prompt_returns_complex_data(self, prompt_manager: PromptManager):
        """Test that prompt function returning complex data structures works correctly."""

        def complex_data_prompt(data_type: str) -> str:
            """Generate complex data as string."""
            import json

            data = {"type": data_type, "values": [1, 2, 3], "metadata": {"created": "2024-01-01"}}
            return json.dumps(data, indent=2)

        prompt_manager.add(complex_data_prompt)

        result = await prompt_manager.get("complex_data_prompt", {"data_type": "test"})

        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        # Should contain the JSON data
        assert isinstance(result.messages[0].content, types.TextContent)
        content_text = result.messages[0].content.text
        assert "test" in content_text
        assert "1" in content_text and "2" in content_text and "3" in content_text
        assert "2024-01-01" in content_text

    async def test_get_prompt_function_raises_exception(self, prompt_manager: PromptManager):
        """Test that exceptions in prompt functions are properly handled."""

        def failing_prompt(should_fail: str) -> str:
            """A prompt that fails."""
            if should_fail == "yes":
                raise Exception("Intentional failure")
            return "Success"

        prompt_manager.add(failing_prompt)

        with pytest.raises(MCPRuntimeError, match="Error getting prompt failing_prompt"):
            await prompt_manager.get("failing_prompt", {"should_fail": "yes"})

    def test_prompt_options_typed_dict(self):
        """Test PromptDefinition TypedDict structure."""
        # This tests the type structure - mainly for documentation
        options: PromptDefinition = {
            "name": "test_name",
            "title": "Test Title",
            "description": "test_description",
            "meta": {"version": "1.0"},
        }

        assert options["name"] == "test_name"
        assert options["title"] == "Test Title"
        assert options["description"] == "test_description"
        assert options["meta"] == {"version": "1.0"}

    def test_decorator_usage(self, prompt_manager: PromptManager):
        """Test using PromptManager as a decorator."""

        @prompt_manager(name="decorated_prompt", title="Decorated")
        def decorated_function(message: str) -> str:
            """A decorated prompt function."""
            return f"Decorated: {message}"

        # Verify the prompt was added
        assert "decorated_prompt" in prompt_manager._prompts
        prompt, _ = prompt_manager._prompts["decorated_prompt"]
        assert prompt.name == "decorated_prompt"
        assert prompt.title == "Decorated"
        assert prompt.description == "A decorated prompt function."

    async def test_decorator_with_no_arguments(self, prompt_manager: PromptManager):
        """Test using PromptManager decorator with a handler that accepts no arguments."""

        @prompt_manager(name="no_args_prompt", title="No Args Prompt")
        def no_args_function() -> str:
            """A prompt function that takes no arguments."""
            return "This is a static prompt with no parameters"

        # Verify the prompt was added
        assert "no_args_prompt" in prompt_manager._prompts
        prompt, _ = prompt_manager._prompts["no_args_prompt"]
        assert prompt.name == "no_args_prompt"
        assert prompt.title == "No Args Prompt"
        assert prompt.description == "A prompt function that takes no arguments."

        # Verify the prompt has no arguments
        assert prompt.arguments == []

        # Verify the prompt can be called without arguments
        result = await prompt_manager.get("no_args_prompt", {})
        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "This is a static prompt with no parameters"

    async def test_full_workflow(self, prompt_manager: PromptManager):
        """Test a complete workflow: add, list, get, remove."""

        def story_prompt(genre: str, character: str, setting: str = "modern day") -> str:
            """Generate a story prompt."""
            return f"Write a {genre} story about {character} set in {setting}"

        # Add prompt
        added_prompt = prompt_manager.add(story_prompt, title="Story Generator")
        assert added_prompt.name == "story_prompt"
        assert added_prompt.title == "Story Generator"

        # List prompts
        prompts = prompt_manager.list()
        assert len(prompts) == 1
        assert prompts[0] == added_prompt

        # Get prompt
        result = await prompt_manager.get("story_prompt", {"genre": "sci-fi", "character": "a robot"})
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Write a sci-fi story about a robot set in modern day"

        result = await prompt_manager.get(
            "story_prompt", {"genre": "fantasy", "character": "a wizard", "setting": "medieval times"}
        )
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Write a fantasy story about a wizard set in medieval times"

        # Remove prompt
        removed_prompt = prompt_manager.remove("story_prompt")
        assert removed_prompt == added_prompt

        # Verify it's gone
        prompts = prompt_manager.list()
        assert len(prompts) == 0

        # Getting removed prompt should fail
        with pytest.raises(PrimitiveError, match="Unknown prompt: story_prompt"):
            await prompt_manager.get("story_prompt", {"genre": "mystery", "character": "detective"})

    def test_convert_result_edge_cases(self, prompt_manager: PromptManager):
        """Test _convert_result method with various edge cases."""

        # Test with single string
        result = prompt_manager._convert_result("Hello world")
        assert len(result) == 1
        assert result[0].role == "user"
        assert isinstance(result[0].content, types.TextContent)
        assert result[0].content.text == "Hello world"

        # Test with tuple
        result = prompt_manager._convert_result(("Message 1", "Message 2"))
        assert len(result) == 2
        assert isinstance(result[0].content, types.TextContent)
        assert result[0].content.text == "Message 1"
        assert isinstance(result[1].content, types.TextContent)
        assert result[1].content.text == "Message 2"

        # Test with mixed types
        mixed_input = [
            "String message",
            {"role": "assistant", "content": {"type": "text", "text": "Assistant message"}},
            types.PromptMessage(role="user", content=types.TextContent(type="text", text="User message")),
        ]
        result = prompt_manager._convert_result(mixed_input)
        assert len(result) == 3
        assert isinstance(result[0].content, types.TextContent)
        assert result[0].content.text == "String message"
        assert result[1].role == "assistant"
        assert isinstance(result[1].content, types.TextContent)
        assert result[2].role == "user"
        assert isinstance(result[2].content, types.TextContent)

    def test_convert_result_invalid_data_raises_error(self, prompt_manager: PromptManager):
        """Test that _convert_result raises MCPRuntimeError for invalid data."""

        # Mock the validation to fail
        invalid_dict = {"invalid": "structure"}

        with pytest.raises(MCPRuntimeError, match="Could not convert prompt result to message"):
            prompt_manager._convert_result([invalid_dict])

    def test_convert_result_with_complex_objects(self, prompt_manager: PromptManager):
        """Test _convert_result with complex objects that need JSON serialization."""
        from pydantic import BaseModel

        class CustomData(BaseModel):
            name: str
            value: int

        custom_obj = CustomData(name="test", value=42)

        result = prompt_manager._convert_result(custom_obj)
        assert len(result) == 1
        assert result[0].role == "user"
        assert isinstance(result[0].content, types.TextContent)
        # Should contain JSON representation
        assert "test" in result[0].content.text
        assert "42" in result[0].content.text

    def test_convert_result_empty_list(self, prompt_manager: PromptManager):
        """Test _convert_result with empty list."""
        result = prompt_manager._convert_result([])
        assert len(result) == 0

    async def test_get_prompt_returns_empty_list(self, prompt_manager: PromptManager):
        """Test prompt function that returns empty list."""

        def empty_prompt(topic: str) -> list[str]:
            """A prompt that returns empty list."""
            return []

        prompt_manager.add(empty_prompt)

        result = await prompt_manager.get("empty_prompt", {"topic": "test"})
        assert len(result.messages) == 0

    async def test_prompt_function_exception_wrapped(self, prompt_manager: PromptManager):
        """Test that exceptions from prompt functions are wrapped in MCPRuntimeError."""

        def failing_prompt(should_fail: bool) -> str:
            """A prompt that can fail."""
            if should_fail:
                raise ValueError("Something went wrong")
            return "Success"

        prompt_manager.add(failing_prompt)

        # Should succeed when not failing
        result = await prompt_manager.get("failing_prompt", {"should_fail": False})  # type: ignore[arg-type]
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "Success"

        # Should wrap exception in MCPRuntimeError
        with pytest.raises(MCPRuntimeError, match="Error getting prompt failing_prompt") as exc_info:
            await prompt_manager.get("failing_prompt", {"should_fail": True})  # type: ignore[arg-type]
        assert isinstance(exc_info.value.__cause__, ValueError)

    async def test_async_prompt_exception_wrapped(self, prompt_manager: PromptManager):
        """Test that exceptions from async prompt functions are wrapped in MCPRuntimeError."""

        async def async_failing_prompt(should_fail: bool) -> str:
            """An async prompt that can fail."""
            await anyio.sleep(0.001)
            if should_fail:
                raise RuntimeError("Async error")
            return "Success"

        prompt_manager.add(async_failing_prompt)

        # Should wrap exception in MCPRuntimeError
        with pytest.raises(MCPRuntimeError, match="Error getting prompt async_failing_prompt") as exc_info:
            await prompt_manager.get("async_failing_prompt", {"should_fail": True})  # type: ignore[arg-type]
        assert isinstance(exc_info.value.__cause__, RuntimeError)


class TestPromptManagerAdvancedFeatures:
    """Test suite for advanced PromptManager features inspired by FastMCP patterns."""

    @pytest.fixture
    def mock_core(self) -> Mock:
        """Create a mock Server for testing."""
        core = Mock(spec=Server)
        core.list_prompts = Mock(return_value=Mock())
        core.get_prompt = Mock(return_value=Mock())
        return core

    @pytest.fixture
    def prompt_manager(self, mock_core: Mock) -> PromptManager:
        """Create a PromptManager instance with mocked core."""
        return PromptManager(mock_core)

    def test_add_prompt_with_title_field(self, prompt_manager: PromptManager):
        """Test that prompts can have a title field for display."""

        def code_review(code: str) -> str:
            """Review code for issues"""
            return f"Reviewing: {code}"

        result = prompt_manager.add(code_review, title="🔍 Code Review Assistant")

        assert result.name == "code_review"
        assert result.title == "🔍 Code Review Assistant"
        assert result.description == "Review code for issues"

    def test_add_prompt_with_field_descriptions(self, prompt_manager: PromptManager):
        """Test that Field descriptions work in prompt parameters."""
        from pydantic import Field

        def detailed_prompt(
            topic: str = Field(description="The main topic to discuss"),
            context: str = Field(description="Additional context", default=""),
        ) -> str:
            """A detailed prompt"""
            return f"Let's discuss {topic}. Context: {context}"

        result = prompt_manager.add(detailed_prompt)

        assert result.arguments is not None

        # Check that parameter descriptions are present
        assert len(result.arguments) == 2
        args_by_name = {arg.name: arg for arg in result.arguments}

        assert "topic" in args_by_name
        assert args_by_name["topic"].description == "The main topic to discuss"
        assert args_by_name["topic"].required is True

        assert "context" in args_by_name
        assert args_by_name["context"].description == "Additional context"
        assert args_by_name["context"].required is False

    async def test_prompt_with_unicode_content(self, prompt_manager: PromptManager):
        """Test that prompts handle Unicode content correctly."""

        def unicode_prompt(topic: str) -> str:
            """Prompt with Unicode characters"""
            return f"{topic} के बारे में एक अनुच्छेद लिखें"

        prompt_manager.add(unicode_prompt, description="अनुच्छेद लेखक ✍️")

        result = await prompt_manager.get("unicode_prompt", {"topic": "🎨 चित्रकला"})

        assert len(result.messages) == 1
        assert isinstance(result.messages[0].content, types.TextContent)
        assert result.messages[0].content.text == "🎨 चित्रकला के बारे में एक अनुच्छेद लिखें"
        assert result.description == "अनुच्छेद लेखक ✍️"

    async def test_prompt_returns_multiple_messages(self, prompt_manager: PromptManager):
        """Test prompt that returns multiple messages."""

        def multi_message_prompt(topic: str) -> list[str]:
            """Prompt that returns multiple messages"""
            return [
                f"First message about {topic}",
                f"Second message about {topic}",
                f"Third message about {topic}",
            ]

        prompt_manager.add(multi_message_prompt)

        result = await prompt_manager.get("multi_message_prompt", {"topic": "testing"})

        assert len(result.messages) == 3
        for message in result.messages:
            assert "testing" in str(message)

    def test_prompt_with_metadata(self, prompt_manager: PromptManager):
        """Test that prompts can have metadata."""

        def meta_prompt(topic: str) -> str:
            """Prompt with metadata"""
            return f"Discuss {topic}"

        meta = {"version": "1.0", "category": "discussion"}
        result = prompt_manager.add(meta_prompt, meta=meta)

        assert result.meta is not None
        assert result.meta == meta
        assert result.meta["version"] == "1.0"
        assert result.meta["category"] == "discussion"

    def test_add_prompt_with_custom_name_and_description(self, prompt_manager: PromptManager):
        """Test adding prompt with custom name and description overrides."""

        def generic_func(input_text: str) -> str:
            return f"Processed: {input_text}"

        result = prompt_manager.add(
            generic_func,
            name="custom_prompt_name",
            description="Custom description for this prompt",
        )

        assert result.name == "custom_prompt_name"
        assert result.description == "Custom description for this prompt"

    async def test_prompt_with_no_arguments(self, prompt_manager: PromptManager):
        """Test prompt with no arguments."""

        def no_args_prompt() -> str:
            """A prompt with no arguments"""
            return "This is a static prompt"

        result = prompt_manager.add(no_args_prompt)

        assert result.arguments is not None
        assert len(result.arguments) == 0

        # Should be callable with empty args
        get_result = await prompt_manager.get("no_args_prompt", None)
        assert len(get_result.messages) == 1

    def test_get_arguments_without_properties(self, prompt_manager: PromptManager):
        """Test _get_arguments when input_schema has no properties.

        A function with no parameters will naturally have an input_schema
        without a 'properties' key, which tests the branch where
        'properties' is not in input_schema.
        """

        def simple_func() -> str:
            """A simple function with no parameters"""
            return "result"

        mcp_func = MCPFunc(simple_func)

        # Verify the schema doesn't have properties (or has empty properties)
        # This tests the code path where "properties" not in input_schema
        arguments = prompt_manager._get_arguments(mcp_func)
        assert arguments == []

    def test_get_arguments_with_properties(self, prompt_manager: PromptManager):
        """Test _get_arguments when input_schema has properties.

        A function with parameters will have an input_schema with a 'properties'
        key, which tests the normal code path where arguments are extracted.
        """

        def func_with_params(
            name: str = Field(description="The user's name"),
            age: int = Field(description="The user's age"),
            email: str = Field(default="", description="Optional email"),
        ) -> str:
            """A function with multiple parameters"""
            return f"{name}, {age}, {email}"

        mcp_func = MCPFunc(func_with_params)

        # Test that arguments are correctly extracted from the schema
        arguments = prompt_manager._get_arguments(mcp_func)

        # Should have 3 arguments
        assert len(arguments) == 3

        # Verify each argument
        name_arg = next(arg for arg in arguments if arg.name == "name")
        assert name_arg.description == "The user's name"
        assert name_arg.required is True

        age_arg = next(arg for arg in arguments if arg.name == "age")
        assert age_arg.description == "The user's age"
        assert age_arg.required is True

        email_arg = next(arg for arg in arguments if arg.name == "email")
        assert email_arg.description == "Optional email"
        assert email_arg.required is False  # Has default value

    async def test_validate_args_with_none(self, prompt_manager: PromptManager):
        """Test _validate_args when prompt_arguments is None."""
        # This should return early without raising an error
        prompt_manager._validate_args(None, {"some": "args"})
        prompt_manager._validate_args(None, None)
        # If we get here without exception, the test passes
