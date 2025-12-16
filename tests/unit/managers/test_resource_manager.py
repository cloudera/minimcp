from typing import Any
from unittest.mock import Mock

import anyio
import mcp.types as types
import pytest
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.lowlevel.server import Server

from minimcp.exceptions import (
    InvalidArgumentsError,
    MCPFuncError,
    MCPRuntimeError,
    PrimitiveError,
    ResourceNotFoundError,
)
from minimcp.managers.resource_manager import ResourceDefinition, ResourceManager, _uri_to_pattern

pytestmark = pytest.mark.anyio


class TestResourceManager:
    """Test suite for ResourceManager class."""

    @pytest.fixture
    def mock_core(self) -> Mock:
        """Create a mock Server for testing."""
        core = Mock(spec=Server)
        core.list_resources = Mock(return_value=Mock())
        core.list_resource_templates = Mock(return_value=Mock())
        core.read_resource = Mock(return_value=Mock())
        return core

    @pytest.fixture
    def resource_manager(self, mock_core: Mock) -> ResourceManager:
        """Create a ResourceManager instance with mocked core."""
        return ResourceManager(mock_core)

    def test_init_hooks_core_methods(self, mock_core: Mock):
        """Test that ResourceManager properly hooks into Server methods."""
        resource_manager = ResourceManager(mock_core)

        # Verify that core methods were called to register handlers
        mock_core.list_resources.assert_called_once()
        mock_core.list_resource_templates.assert_called_once()
        mock_core.read_resource.assert_called_once()

        # Verify internal state
        assert resource_manager._resources == {}

    def test_add_basic_resource(self, resource_manager: ResourceManager):
        """Test adding a basic resource without parameters."""

        def sample_resource() -> str:
            """A sample resource for testing."""
            return "Sample content"

        result = resource_manager.add(sample_resource, "file://test.txt")

        # Verify the returned resource
        assert isinstance(result, types.Resource)
        assert result.name == "sample_resource"
        assert str(result.uri) == "file://test.txt/"
        assert result.description == "A sample resource for testing."
        assert result.title is None
        assert result.mimeType is None
        assert result.annotations is None
        assert result.meta is None

        # Verify internal state
        assert "sample_resource" in resource_manager._resources
        resource_details = resource_manager._resources["sample_resource"]
        assert resource_details.resource == result
        assert resource_details.func.func == sample_resource
        assert resource_details.normalized_uri == "file://test.txt"
        assert resource_details.uri_pattern is None

    def test_add_resource_template(self, resource_manager: ResourceManager):
        """Test adding a resource template with parameters."""

        def user_profile(user_id: str) -> dict[str, Any]:
            """Get user profile data."""
            return {"id": user_id, "name": f"User {user_id}"}

        result = resource_manager.add(user_profile, "users/{user_id}/profile")

        # Verify the returned resource template
        assert isinstance(result, types.ResourceTemplate)
        assert result.name == "user_profile"
        assert result.uriTemplate == "users/{user_id}/profile"
        assert result.description == "Get user profile data."

        # Verify internal state
        assert "user_profile" in resource_manager._resources
        resource_details = resource_manager._resources["user_profile"]
        assert resource_details.resource == result
        assert resource_details.normalized_uri == "users/|/profile"
        assert resource_details.uri_pattern is not None

    def test_add_resource_with_custom_options(self, resource_manager: ResourceManager):
        """Test adding a resource with custom options."""

        def json_data() -> dict[str, Any]:
            return {"data": "value"}

        custom_annotations = types.Annotations(audience=["user"])
        custom_meta = {"version": "1.0"}

        result = resource_manager.add(
            json_data,
            "data://json",
            title="JSON Data",
            description="Custom JSON data",
            mime_type="application/json",
            annotations=custom_annotations,
            meta=custom_meta,
        )

        assert result.title == "JSON Data"
        assert result.description == "Custom JSON data"
        assert result.mimeType == "application/json"
        assert result.annotations == custom_annotations
        assert result.meta == custom_meta

    def test_add_resource_without_docstring(self, resource_manager: ResourceManager):
        """Test adding a resource without docstring uses None as description."""

        def no_doc_resource() -> str:
            return "content"

        result = resource_manager.add(no_doc_resource, "file://nodoc.txt")
        assert result.description is None

    def test_add_async_resource(self, resource_manager: ResourceManager):
        """Test adding an async function as a resource."""

        async def async_resource(delay: float) -> str:
            """An async resource."""
            await anyio.sleep(delay)
            return "async content"

        result = resource_manager.add(async_resource, "async/{delay}")

        assert isinstance(result, types.ResourceTemplate)
        assert result.name == "async_resource"
        assert result.description == "An async resource."
        assert "async_resource" in resource_manager._resources

    def test_add_resource_template_with_complex_parameter_types(self, resource_manager: ResourceManager):
        """Test resource templates with complex parameter types."""

        # Note: Resource templates typically only support string parameters from URI
        # But the function can have complex types that accept string values
        def search_resource(query: str, page: str) -> dict[str, Any]:
            """Search with query and page."""
            return {"query": query, "page": int(page), "results": []}

        result = resource_manager.add(search_resource, "search/{query}/{page}")

        assert isinstance(result, types.ResourceTemplate)
        assert result.name == "search_resource"
        assert result.uriTemplate == "search/{query}/{page}"

    def test_add_resource_empty_uri_raises_error(self, resource_manager: ResourceManager):
        """Test that adding a resource with empty URI raises PrimitiveError."""

        def test_resource() -> str:
            return "content"

        with pytest.raises(PrimitiveError, match="URI is required"):
            resource_manager.add(test_resource, "")

    def test_add_duplicate_resource_name_raises_error(self, resource_manager: ResourceManager):
        """Test that adding a resource with duplicate name raises PrimitiveError."""

        def resource1() -> str:
            return "content1"

        def resource2() -> str:
            return "content2"

        # Add first resource
        resource_manager.add(resource1, "file://test1.txt", name="duplicate_name")  # type: ignore

        # Adding second resource with same name should raise error
        with pytest.raises(PrimitiveError, match="Resource duplicate_name already registered"):
            resource_manager.add(resource2, "file://test2.txt", name="duplicate_name")  # type: ignore

    def test_add_duplicate_uri_raises_error(self, resource_manager: ResourceManager):
        """Test that adding resources with duplicate normalized URI raises PrimitiveError."""

        def resource1() -> str:
            return "content1"

        def resource2() -> str:
            return "content2"

        # Add first resource
        resource_manager.add(resource1, "file://test.txt")

        # Adding second resource with same URI should raise error
        with pytest.raises(PrimitiveError, match="Resource file://test.txt already registered"):
            resource_manager.add(resource2, "file://test.txt")

    def test_add_lambda_without_name_raises_error(self, resource_manager: ResourceManager):
        """Test that lambda functions without custom name are rejected by MCPFunc."""
        lambda_resource: Any = lambda: "content"  # noqa: E731  # type: ignore[misc]

        with pytest.raises(MCPFuncError, match="Lambda functions must be named"):
            resource_manager.add(lambda_resource, "file://lambda.txt")  # type: ignore[arg-type]

    def test_add_lambda_with_custom_name_succeeds(self, resource_manager: ResourceManager):
        """Test that lambda functions with custom name work."""
        lambda_resource: Any = lambda: "Lambda content"  # noqa: E731  # type: ignore[misc]

        result = resource_manager.add(lambda_resource, "file://lambda.txt", name="custom_lambda")  # type: ignore[arg-type]
        assert result.name == "custom_lambda"
        assert "custom_lambda" in resource_manager._resources

    def test_add_function_with_var_args_raises_error(self, resource_manager: ResourceManager):
        """Test that functions with *args are rejected by MCPFunc."""

        def resource_with_args(id: str, *args: str) -> str:
            return f"Content {id}"

        with pytest.raises(MCPFuncError, match="Functions with \\*args are not supported"):
            resource_manager.add(resource_with_args, "items/{id}")

    def test_add_function_with_kwargs_raises_error(self, resource_manager: ResourceManager):
        """Test that functions with **kwargs are rejected by MCPFunc."""

        def resource_with_kwargs(id: str, **kwargs: Any) -> str:
            return f"Content {id}"

        with pytest.raises(MCPFuncError, match="Functions with \\*\\*kwargs are not supported"):
            resource_manager.add(resource_with_kwargs, "items/{id}")

    def test_add_bound_method_as_resource(self, resource_manager: ResourceManager):
        """Test that bound instance methods can be added as resources."""

        class DataProvider:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def get_data(self) -> str:
                """Get data with prefix."""
                return f"{self.prefix}: data"

        provider = DataProvider("TestPrefix")
        result = resource_manager.add(provider.get_data, "data://test")

        assert result.name == "get_data"
        assert result.description == "Get data with prefix."
        assert "get_data" in resource_manager._resources

    def test_add_lambda_template_with_custom_name(self, resource_manager: ResourceManager):
        """Test lambda with parameters as resource template."""
        lambda_template: Any = lambda id: f"Item {id}"  # noqa: E731  # type: ignore[misc]

        result = resource_manager.add(lambda_template, "items/{id}", name="lambda_template")  # type: ignore[arg-type]
        assert isinstance(result, types.ResourceTemplate)
        assert result.name == "lambda_template"
        assert "lambda_template" in resource_manager._resources

    def test_add_duplicate_template_uri_raises_error(self, resource_manager: ResourceManager):
        """Test that adding resource templates with duplicate normalized URI raises PrimitiveError."""

        def template1(id: str) -> str:
            return f"content1-{id}"

        def template2(id: str) -> str:
            return f"content2-{id}"

        # Add first template
        resource_manager.add(template1, "files/{id}")

        # Adding second template with same normalized URI should raise error
        with pytest.raises(PrimitiveError, match="Resource files/\\{id\\} already registered"):
            resource_manager.add(template2, "files/{id}")

    def test_add_template_parameter_mismatch_raises_error(self, resource_manager: ResourceManager):
        """Test that parameter mismatch between URI and function raises PrimitiveError."""

        def mismatched_func(user_id: str, extra_param: str) -> str:
            return f"{user_id}-{extra_param}"

        with pytest.raises(PrimitiveError, match="Mismatch between URI parameters"):
            resource_manager.add(mismatched_func, "users/{user_id}")

        def another_mismatch(wrong_param: str) -> str:
            return wrong_param

        with pytest.raises(PrimitiveError, match="Mismatch between URI parameters"):
            resource_manager.add(another_mismatch, "users/{user_id}")

    def test_remove_existing_resource(self, resource_manager: ResourceManager):
        """Test removing an existing resource."""

        def test_resource() -> str:
            return "content"

        # Add resource first
        added_resource = resource_manager.add(test_resource, "file://test.txt")
        assert "test_resource" in resource_manager._resources

        # Remove the resource
        removed_resource = resource_manager.remove("test_resource")

        assert removed_resource == added_resource
        assert "test_resource" not in resource_manager._resources

    def test_remove_nonexistent_resource_raises_error(self, resource_manager: ResourceManager):
        """Test that removing a non-existent resource raises PrimitiveError."""
        with pytest.raises(PrimitiveError, match="Unknown resource: nonexistent"):
            resource_manager.remove("nonexistent")

    async def test_list_resources_empty(self, resource_manager: ResourceManager):
        """Test listing resources when no resources are registered."""
        result = resource_manager.list()
        assert result == []

        # Test async version
        async_result = await resource_manager._async_list()
        assert async_result == []

    async def test_list_resources_with_multiple_resources(self, resource_manager: ResourceManager):
        """Test listing resources when multiple resources are registered."""

        def resource1() -> str:
            return "content1"

        def resource2() -> str:
            return "content2"

        def template1(id: str) -> str:
            return f"template-{id}"

        added_resource1 = resource_manager.add(resource1, "file://test1.txt")
        added_resource2 = resource_manager.add(resource2, "file://test2.txt")
        # Template should not appear in regular list
        resource_manager.add(template1, "templates/{id}")

        result = resource_manager.list()

        assert len(result) == 2
        assert added_resource1 in result
        assert added_resource2 in result

        # Test async version
        async_result = await resource_manager._async_list()
        assert len(async_result) == 2
        assert added_resource1 in async_result
        assert added_resource2 in async_result

    async def test_list_resource_templates_empty(self, resource_manager: ResourceManager):
        """Test listing resource templates when no templates are registered."""
        result = resource_manager.list_templates()
        assert result == []

        # Test async version
        async_result = await resource_manager._async_list_templates()
        assert async_result == []

    async def test_list_resource_templates_with_multiple_templates(self, resource_manager: ResourceManager):
        """Test listing resource templates when multiple templates are registered."""

        def template1(id: str) -> str:
            return f"template1-{id}"

        def template2(name: str) -> str:
            return f"template2-{name}"

        def regular_resource() -> str:
            return "regular content"

        added_template1 = resource_manager.add(template1, "templates/{id}")
        added_template2 = resource_manager.add(template2, "items/{name}")
        # Regular resource should not appear in template list
        resource_manager.add(regular_resource, "file://regular.txt")

        result = resource_manager.list_templates()

        assert len(result) == 2
        assert added_template1 in result
        assert added_template2 in result

        # Test async version
        async_result = await resource_manager._async_list_templates()
        assert len(async_result) == 2
        assert added_template1 in async_result
        assert added_template2 in async_result

    async def test_read_resource_sync_function(self, resource_manager: ResourceManager):
        """Test reading a synchronous resource."""

        def text_resource() -> str:
            """A text resource."""
            return "Hello, World!"

        resource_manager.add(text_resource, "file://hello.txt", mime_type="text/plain")

        result = await resource_manager.read("file://hello.txt")
        result_list = list(result)

        assert len(result_list) == 1
        assert isinstance(result_list[0], ReadResourceContents)
        assert result_list[0].content == "Hello, World!"
        assert result_list[0].mime_type == "text/plain"

    async def test_read_resource_async_function(self, resource_manager: ResourceManager):
        """Test reading an asynchronous resource."""

        async def async_text_resource() -> str:
            """An async text resource."""
            await anyio.sleep(0.01)  # Small delay to make it actually async
            return "Async Hello, World!"

        resource_manager.add(async_text_resource, "file://async_hello.txt")

        result = await resource_manager.read("file://async_hello.txt")
        result_list = list(result)

        assert len(result_list) == 1
        assert result_list[0].content == "Async Hello, World!"

    async def test_read_resource_template_with_parameters(self, resource_manager: ResourceManager):
        """Test reading a resource template with parameters."""

        def user_data(user_id: str, format: str) -> dict[str, Any]:
            """Get user data in specified format."""
            return {"id": user_id, "format": format, "data": f"User {user_id} data"}

        resource_manager.add(user_data, "users/{user_id}/{format}")

        result = await resource_manager.read("users/123/json")
        result_list = list(result)

        assert len(result_list) == 1
        content = result_list[0].content
        # Should be JSON serialized
        content_str = content if isinstance(content, str) else content.decode()
        assert "123" in content_str
        assert "json" in content_str
        assert "User 123 data" in content_str

    async def test_read_resource_bytes_content(self, resource_manager: ResourceManager):
        """Test reading a resource that returns bytes."""

        def binary_resource() -> bytes:
            """A binary resource."""
            return b"Binary content"

        resource_manager.add(binary_resource, "file://binary.dat", mime_type="application/octet-stream")

        result = await resource_manager.read("file://binary.dat")
        result_list = list(result)

        assert len(result_list) == 1
        assert result_list[0].content == b"Binary content"
        assert result_list[0].mime_type == "application/octet-stream"

    async def test_read_resource_complex_data(self, resource_manager: ResourceManager):
        """Test reading a resource that returns complex data structures."""

        def json_resource() -> dict[str, Any]:
            """A JSON resource."""
            return {"name": "Test Resource", "values": [1, 2, 3], "metadata": {"created": "2024-01-01"}}

        resource_manager.add(json_resource, "data://json", mime_type="application/json")

        result = await resource_manager.read("data://json")
        result_list = list(result)

        assert len(result_list) == 1
        content = result_list[0].content
        content_str = content if isinstance(content, str) else content.decode()
        assert "Test Resource" in content_str
        assert result_list[0].mime_type == "application/json"

    async def test_read_nonexistent_resource_raises_error(self, resource_manager: ResourceManager):
        """Test that reading a non-existent resource raises PrimitiveError."""
        with pytest.raises(ResourceNotFoundError, match="Resource not found"):
            await resource_manager.read("file://nonexistent.txt")

    async def test_read_by_name_existing_resource(self, resource_manager: ResourceManager):
        """Test reading a resource by name."""

        def named_resource() -> str:
            return "Named content"

        resource_manager.add(named_resource, "file://named.txt")

        result = await resource_manager.read_by_name("named_resource")
        result_list = list(result)

        assert len(result_list) == 1
        assert result_list[0].content == "Named content"

    async def test_read_by_name_template_with_args(self, resource_manager: ResourceManager):
        """Test reading a resource template by name with arguments."""

        def template_resource(item_id: str, category: str) -> str:
            return f"Item {item_id} in category {category}"

        resource_manager.add(template_resource, "items/{item_id}/{category}")

        result = await resource_manager.read_by_name("template_resource", {"item_id": "123", "category": "books"})
        result_list = list(result)

        assert len(result_list) == 1
        assert result_list[0].content == "Item 123 in category books"

    async def test_read_by_name_nonexistent_raises_error(self, resource_manager: ResourceManager):
        """Test that reading a non-existent resource by name raises PrimitiveError."""
        with pytest.raises(ResourceNotFoundError, match="Resource nonexistent not found"):
            await resource_manager.read_by_name("nonexistent")

    async def test_read_resource_function_raises_exception(self, resource_manager: ResourceManager):
        """Test that exceptions in resource functions are properly handled."""

        def failing_resource() -> str:
            """A resource that fails."""
            raise RuntimeError("Intentional failure")

        resource_manager.add(failing_resource, "file://failing.txt")

        with pytest.raises(MCPRuntimeError, match="Error reading resource failing_resource"):
            await resource_manager.read("file://failing.txt")

    async def test_read_resource_with_type_validation(self, resource_manager: ResourceManager):
        """Test that argument types are validated during resource reading."""

        def typed_resource(count: int, name: str) -> str:
            """A resource with strict types."""
            return f"Item {count}: {name}"

        resource_manager.add(typed_resource, "items/{count}/{name}")

        # String numbers should be coerced to int by pydantic
        result = await resource_manager.read("items/42/test")
        result_list = list(result)
        assert len(result_list) == 1
        content_str = (
            result_list[0].content if isinstance(result_list[0].content, str) else result_list[0].content.decode()
        )
        assert "Item 42: test" in content_str

        with pytest.raises(InvalidArgumentsError, match="Input should be a valid integer"):
            await resource_manager.read("items/not_a_number/test")

    async def test_read_bound_method_resource(self, resource_manager: ResourceManager):
        """Test reading a resource that is a bound method."""

        class ContentGenerator:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def generate(self, item_id: str) -> str:
                """Generate content with prefix."""
                return f"{self.prefix}: Content for {item_id}"

        generator = ContentGenerator("PREFIX")
        resource_manager.add(generator.generate, "content/{item_id}")

        result = await resource_manager.read("content/123")
        result_list = list(result)

        assert len(result_list) == 1
        assert result_list[0].content == "PREFIX: Content for 123"

    async def test_read_async_resource_exception_wrapped(self, resource_manager: ResourceManager):
        """Test that exceptions from async resource functions are wrapped in MCPRuntimeError."""

        async def async_failing_resource(should_fail: str) -> str:
            """An async resource that can fail."""
            await anyio.sleep(0.001)
            if should_fail == "yes":
                raise ValueError("Async failure")
            return "Success"

        resource_manager.add(async_failing_resource, "async/{should_fail}")

        # Should succeed when not failing
        result = await resource_manager.read("async/no")
        result_list = list(result)
        assert result_list[0].content == "Success"

        # Should wrap exception in MCPRuntimeError
        with pytest.raises(MCPRuntimeError, match="Error reading resource async_failing_resource") as exc_info:
            await resource_manager.read("async/yes")
        assert isinstance(exc_info.value.__cause__, ValueError)

    async def test_read_resource_missing_template_parameters(self, resource_manager: ResourceManager):
        """Test that missing required parameters raises an error."""

        def multi_param_resource(id: str, category: str, format: str) -> str:
            """A resource with multiple parameters."""
            return f"{category}-{id}.{format}"

        resource_manager.add(multi_param_resource, "items/{id}/{category}/{format}")

        # Correct parameters should work
        result = await resource_manager.read("items/123/books/json")
        result_list = list(result)
        content_str = (
            result_list[0].content if isinstance(result_list[0].content, str) else result_list[0].content.decode()
        )
        assert "books-123.json" in content_str

        # URI that doesn't match pattern should fail with "not found"
        with pytest.raises(ResourceNotFoundError, match="Resource not found"):
            await resource_manager.read("items/123")

    async def test_read_by_name_with_type_coercion(self, resource_manager: ResourceManager):
        """Test reading by name with type coercion."""

        def numeric_resource(count: int, multiplier: float) -> str:
            """A resource with numeric parameters."""
            result = count * multiplier
            return f"Result: {result}"

        resource_manager.add(numeric_resource, "calc/{count}/{multiplier}")

        # Pydantic should coerce strings to numbers
        result = await resource_manager.read_by_name("numeric_resource", {"count": "10", "multiplier": "2.5"})
        result_list = list(result)
        content_str = (
            result_list[0].content if isinstance(result_list[0].content, str) else result_list[0].content.decode()
        )
        assert "Result: 25.0" in content_str

    async def test_read_resource_with_optional_parameters(self, resource_manager: ResourceManager):
        """Test resource templates with optional parameters."""

        def resource_with_defaults(id: str, format: str = "json") -> str:
            """A resource with default parameter."""
            return f"Item {id} in {format} format"

        # Since URI templates require all parameters, optional params in function
        # should match required params in URI template
        resource_manager.add(resource_with_defaults, "items/{id}/{format}")

        result = await resource_manager.read("items/123/xml")
        result_list = list(result)
        content_str = (
            result_list[0].content if isinstance(result_list[0].content, str) else result_list[0].content.decode()
        )
        assert "Item 123 in xml format" in content_str

    def test_resource_options_typed_dict(self):
        """Test ResourceDefinition TypedDict structure."""
        # This tests the type structure - mainly for documentation
        options: ResourceDefinition = {
            "title": "Test Title",
            "description": "test_description",
            "mime_type": "text/plain",
            "annotations": types.Annotations(audience=["user"]),
            "meta": {"version": "1.0"},
        }

        assert options["title"] == "Test Title"
        assert options["description"] == "test_description"
        assert options["mime_type"] == "text/plain"
        assert options["meta"] == {"version": "1.0"}

    def test_decorator_usage(self, resource_manager: ResourceManager):
        """Test using ResourceManager as a decorator."""

        @resource_manager("file://decorated.txt", title="Decorated Resource")
        def decorated_function() -> str:
            """A decorated resource function."""
            return "Decorated content"

        # Verify the resource was added
        assert "decorated_function" in resource_manager._resources
        resource_details = resource_manager._resources["decorated_function"]
        assert resource_details.resource.name == "decorated_function"
        assert resource_details.resource.title == "Decorated Resource"
        assert resource_details.resource.description == "A decorated resource function."

    async def test_decorator_with_no_arguments(self, resource_manager: ResourceManager):
        """Test using ResourceManager decorator with a handler that accepts no arguments."""

        @resource_manager("file://no_args.txt", title="No Args Resource")
        def no_args_function() -> str:
            """A resource function that takes no arguments."""
            return "Static content with no parameters"

        # Verify the resource was added
        assert "no_args_function" in resource_manager._resources
        resource_details = resource_manager._resources["no_args_function"]
        assert resource_details.resource.name == "no_args_function"
        assert resource_details.resource.title == "No Args Resource"
        assert resource_details.resource.description == "A resource function that takes no arguments."
        assert isinstance(resource_details.resource, types.Resource)
        assert str(resource_details.resource.uri).rstrip("/") == "file://no_args.txt"

        # Verify the resource is not a template (has no parameters)
        assert resource_details.uri_pattern is None

        # Verify the resource can be read without arguments
        result = await resource_manager.read("file://no_args.txt")
        result_list = list(result)
        assert len(result_list) == 1
        assert isinstance(result_list[0], ReadResourceContents)
        content_str = (
            result_list[0].content if isinstance(result_list[0].content, str) else result_list[0].content.decode()
        )
        assert content_str == "Static content with no parameters"

    def test_uri_to_pattern_function(self):
        """Test the _uri_to_pattern utility function."""

        # Simple template
        pattern = _uri_to_pattern("users/{id}")
        assert pattern.match("users/123")
        match = pattern.match("users/abc")
        assert match is not None
        assert match.groupdict() == {"id": "abc"}
        assert not pattern.match("users/123/extra")

        # Multiple parameters
        pattern = _uri_to_pattern("users/{user_id}/posts/{post_id}")
        match = pattern.match("users/123/posts/456")
        assert match is not None
        assert match.groupdict() == {"user_id": "123", "post_id": "456"}

        # With special characters
        pattern = _uri_to_pattern("files/{name}.{ext}")
        match = pattern.match("files/document.pdf")
        assert match is not None
        assert match.groupdict() == {"name": "document", "ext": "pdf"}

        # No match cases
        pattern = _uri_to_pattern("users/{id}")
        assert not pattern.match("posts/123")
        assert not pattern.match("users/")
        assert not pattern.match("users/123/")

    def test_convert_result_with_complex_objects(self, resource_manager: ResourceManager):
        """Test _convert_result with complex objects that need JSON serialization."""
        from pydantic import BaseModel

        class CustomData(BaseModel):
            name: str
            value: int

        custom_obj = CustomData(name="test", value=42)

        result = resource_manager._convert_result(custom_obj)
        assert isinstance(result, str | bytes)
        result_str = result if isinstance(result, str) else result.decode()
        # Should contain JSON representation
        assert "test" in result_str
        assert "42" in result_str

    def test_convert_result_with_bytes(self, resource_manager: ResourceManager):
        """Test _convert_result preserves bytes."""
        binary_data = b"Binary content"
        result = resource_manager._convert_result(binary_data)
        assert result == binary_data
        assert isinstance(result, bytes)

    def test_convert_result_with_string(self, resource_manager: ResourceManager):
        """Test _convert_result preserves strings."""
        text_data = "Text content"
        result = resource_manager._convert_result(text_data)
        assert result == text_data
        assert isinstance(result, str)

    async def test_resource_function_exception_with_cause(self, resource_manager: ResourceManager):
        """Test that exception chaining is preserved."""

        def resource_with_nested_error() -> str:
            """A resource that raises a nested exception."""
            try:
                raise ValueError("Inner error")
            except ValueError as e:
                raise RuntimeError("Outer error") from e

        resource_manager.add(resource_with_nested_error, "file://nested.txt")

        with pytest.raises(MCPRuntimeError, match="Error reading resource resource_with_nested_error") as exc_info:
            await resource_manager.read("file://nested.txt")
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert exc_info.value.__cause__.__cause__ is not None

    def test_check_similar_resource(self, resource_manager: ResourceManager):
        """Test the _check_similar_resource method."""

        def sample_resource(id: str) -> str:
            return f"sample content {id}"

        resource_manager.add(sample_resource, name="sample_resource1", uri="users/{id}")

        with pytest.raises(PrimitiveError, match="Resource users/{different_id} already registered"):
            resource_manager.add(sample_resource, "users/{different_id}")

    def test_find_matching_resource_exact_match(self, resource_manager: ResourceManager):
        """Test _find_matching_resource with exact URI match."""

        def static_resource() -> str:
            return "static content"

        resource_manager.add(static_resource, "file://static.txt")

        details, args = resource_manager._find_matching_resource("file://static.txt")
        assert details is not None
        assert args is None
        assert details.resource.name == "static_resource"

    def test_find_matching_resource_template_match(self, resource_manager: ResourceManager):
        """Test _find_matching_resource with template URI match."""

        def template_resource(id: str, format: str) -> str:
            return f"content-{id}-{format}"

        resource_manager.add(template_resource, "items/{id}.{format}")

        details, args = resource_manager._find_matching_resource("items/123.json")
        assert details is not None
        assert args == {"id": "123", "format": "json"}
        assert details.resource.name == "template_resource"

    def test_find_matching_resource_no_match(self, resource_manager: ResourceManager):
        """Test _find_matching_resource with no matching URI."""

        def some_resource() -> str:
            return "content"

        resource_manager.add(some_resource, "file://test.txt")

        with pytest.raises(ResourceNotFoundError, match="Resource not found"):
            resource_manager._find_matching_resource("file://nonexistent.txt")


class TestResourceManagerAdvancedFeatures:
    """Test suite for advanced ResourceManager features inspired by FastMCP patterns."""

    @pytest.fixture
    def mock_core(self) -> Mock:
        """Create a mock Server for testing."""
        core = Mock(spec=Server)
        core.list_resources = Mock(return_value=Mock())
        core.list_resource_templates = Mock(return_value=Mock())
        core.read_resource = Mock(return_value=Mock())
        return core

    @pytest.fixture
    def resource_manager(self, mock_core: Mock) -> ResourceManager:
        """Create a ResourceManager instance with mocked core."""
        return ResourceManager(mock_core)

    def test_add_resource_with_title_field(self, resource_manager: ResourceManager):
        """Test that resources can have a title field for display."""

        def config_resource() -> str:
            """Configuration data"""
            return '{"key": "value"}'

        result = resource_manager.add(config_resource, uri="config://app.json", title="📄 App Configuration")

        assert isinstance(result, types.Resource)
        assert result.name == "config_resource"
        assert result.title == "📄 App Configuration"
        assert str(result.uri) == "config://app.json"

    def test_add_resource_with_annotations(self, resource_manager: ResourceManager):
        """Test that resources can have annotations."""
        from mcp.types import Annotations

        def important_resource() -> str:
            """Important data"""
            return "critical data"

        annotations = Annotations(audience=["assistant"], priority=1.0)
        result = resource_manager.add(
            important_resource,
            uri="data://important",
            annotations=annotations,
        )

        assert result.annotations is not None
        assert result.annotations == annotations
        assert result.annotations.priority == 1.0

    def test_add_resource_template_with_title(self, resource_manager: ResourceManager):
        """Test that resource templates can have titles."""

        def file_resource(path: str) -> str:
            """Read file content"""
            return f"Content of {path}"

        result = resource_manager.add(
            file_resource,
            uri="file:///{path}",
            title="File System Access",
        )

        assert isinstance(result, types.ResourceTemplate)
        assert result.title == "File System Access"
        assert result.uriTemplate == "file:///{path}"

    async def test_resource_with_unicode_content(self, resource_manager: ResourceManager):
        """Test that resources handle Unicode in content (not URIs, which must be ASCII)."""

        def unicode_resource() -> str:
            """Resource with Unicode content"""
            return "Unicode content: लेखक ✍️"

        # URIs must be ASCII-compatible per RFC 3986
        resource_manager.add(unicode_resource, uri="docs://unicode-test")

        result = await resource_manager.read("docs://unicode-test")

        assert isinstance(result, list)
        assert len(result) == 1
        assert "लेखक" in str(result[0].content)
        assert "✍️" in str(result[0].content)

    async def test_resource_template_with_unicode_parameters(self, resource_manager: ResourceManager):
        """Test resource template with Unicode parameter values."""

        def doc_resource(doc_name: str) -> str:
            """Get document"""
            return f"Document: {doc_name}"

        resource_manager.add(doc_resource, uri="docs://{doc_name}")

        # Read with Unicode parameter
        result = await resource_manager.read("docs://समाचार")

        assert isinstance(result, list)
        assert len(result) == 1
        assert "समाचार" in str(result[0].content)

    def test_resource_with_metadata(self, resource_manager: ResourceManager):
        """Test that resources can have metadata."""

        def meta_resource() -> str:
            """Resource with metadata"""
            return "data"

        meta = {"version": "2.0", "source": "database"}
        result = resource_manager.add(meta_resource, uri="db://data", meta=meta)

        assert result.meta is not None
        assert result.meta == meta
        assert result.meta["version"] == "2.0"

    async def test_resource_with_mime_type_json(self, resource_manager: ResourceManager):
        """Test resource with explicit JSON MIME type."""

        def json_resource() -> dict[str, Any]:
            """Return JSON data"""
            return {"status": "ok", "count": 42}

        resource_manager.add(json_resource, uri="api://status", mime_type="application/json")

        result = await resource_manager.read("api://status")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].mime_type == "application/json"
        assert "status" in str(result[0].content)
        assert "ok" in str(result[0].content)

    async def test_resource_with_binary_content(self, resource_manager: ResourceManager):
        """Test resource that returns binary content."""

        def binary_resource() -> bytes:
            """Return binary data"""
            return b"Binary content \x00\x01\x02"

        resource_manager.add(binary_resource, uri="data://binary", mime_type="application/octet-stream")

        result = await resource_manager.read("data://binary")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0].content, bytes)
        assert result[0].content == b"Binary content \x00\x01\x02"
        assert result[0].mime_type == "application/octet-stream"

    async def test_resource_template_with_multiple_parameters(self, resource_manager: ResourceManager):
        """Test resource template with multiple parameters."""

        def multi_param_resource(category: str, item_id: str, format: str) -> str:
            """Resource with multiple parameters"""
            return f"Category: {category}, ID: {item_id}, Format: {format}"

        resource_manager.add(multi_param_resource, uri="data://{category}/{item_id}.{format}")

        result = await resource_manager.read("data://products/123.json")

        assert isinstance(result, list)
        assert len(result) == 1
        assert "Category: products" in str(result[0].content)
        assert "ID: 123" in str(result[0].content)
        assert "Format: json" in str(result[0].content)

    def test_resource_with_custom_name_override(self, resource_manager: ResourceManager):
        """Test adding resource with custom name override."""

        def generic_func() -> str:
            return "data"

        result = resource_manager.add(
            generic_func,
            uri="custom://data",
            name="my_custom_resource_name",
            description="Custom description",
        )

        assert result.name == "my_custom_resource_name"
        assert result.description == "Custom description"

    async def test_full_workflow(self, resource_manager: ResourceManager):
        """Test a complete workflow: add, list, read, remove."""

        def config_resource() -> dict[str, Any]:
            """Application configuration."""
            return {"app_name": "TestApp", "version": "1.0", "debug": True}

        def user_resource(user_id: str) -> dict[str, Any]:
            """User profile data."""
            return {"id": user_id, "name": f"User {user_id}", "active": True}

        # Add resources
        config_added = resource_manager.add(
            config_resource, "config://app.json", title="App Config", mime_type="application/json"
        )
        user_added = resource_manager.add(user_resource, "users/{user_id}")

        assert config_added.name == "config_resource"
        assert isinstance(user_added, types.ResourceTemplate)

        # List resources and templates
        resources = resource_manager.list()
        templates = resource_manager.list_templates()

        assert len(resources) == 1
        assert len(templates) == 1
        assert config_added in resources
        assert user_added in templates

        # Read resources
        config_result = await resource_manager.read("config://app.json")
        config_content = list(config_result)[0]
        config_content_str = (
            config_content.content if isinstance(config_content.content, str) else config_content.content.decode()
        )
        assert "TestApp" in config_content_str
        assert config_content.mime_type == "application/json"

        user_result = await resource_manager.read("users/456")
        user_content = list(user_result)[0]
        user_content_str = (
            user_content.content if isinstance(user_content.content, str) else user_content.content.decode()
        )
        assert "User 456" in user_content_str

        # Read by name
        user_by_name = await resource_manager.read_by_name("user_resource", {"user_id": "789"})
        user_by_name_content = list(user_by_name)[0]
        user_by_name_content_str = (
            user_by_name_content.content
            if isinstance(user_by_name_content.content, str)
            else user_by_name_content.content.decode()
        )
        assert "User 789" in user_by_name_content_str

        # Remove resources
        removed_config = resource_manager.remove("config_resource")
        removed_user = resource_manager.remove("user_resource")

        assert removed_config == config_added
        assert removed_user == user_added

        # Verify they're gone
        assert len(resource_manager.list()) == 0
        assert len(resource_manager.list_templates()) == 0

        # Reading removed resources should fail
        with pytest.raises(ResourceNotFoundError, match="Resource not found"):
            await resource_manager.read("config://app.json")

        with pytest.raises(ResourceNotFoundError, match="Resource user_resource not found"):
            await resource_manager.read_by_name("user_resource", {"user_id": "123"})
