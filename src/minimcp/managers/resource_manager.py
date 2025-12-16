import builtins
import logging
import re
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

import pydantic_core
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.lowlevel.server import Server
from mcp.types import Annotations, AnyFunction, Resource, ResourceTemplate
from pydantic import AnyUrl
from typing_extensions import TypedDict, Unpack

from minimcp.exceptions import InvalidArgumentsError, MCPRuntimeError, PrimitiveError, ResourceNotFoundError
from minimcp.utils.mcp_func import MCPFunc

logger = logging.getLogger(__name__)


class ResourceDefinition(TypedDict, total=False):
    """
    Type definition for resource parameters.

    Attributes:
        name: Optional custom name for the resource. If not provided, the function name is used.
        title: Optional human-readable title for display purposes. Shows in client UIs.
        description: Optional description of what the resource provides. If not provided,
            the function's docstring is used.
        mime_type: Optional MIME type for the resource content (e.g., "text/plain", "application/json",
            "image/png"). For binary data, content will be base64-encoded. Use "inode/directory" for
            directory-like resources.
        annotations: Optional annotations providing hints to clients. Can include:
            - audience: ["user", "assistant"] - intended audience(s)
            - priority: 0.0-1.0 - importance (1.0 = most important)
            - lastModified: ISO 8601 timestamp (e.g., "2025-01-12T15:00:58Z")
        meta: Optional metadata dictionary for additional resource information.
    """

    name: str | None
    title: str | None
    description: str | None
    mime_type: str | None
    annotations: Annotations | None
    meta: dict[str, Any] | None


class _ResourceEntry(NamedTuple):
    """
    Internal container for resource registration details.

    Attributes:
        resource: The Resource or ResourceTemplate object.
        func: The MCPFunc wrapper for the handler function.
        normalized_uri: URI with template parameters replaced for comparison.
        uri_pattern: Compiled regex pattern for matching URIs (only for resource templates).
    """

    resource: Resource | ResourceTemplate
    func: MCPFunc
    normalized_uri: str
    uri_pattern: re.Pattern[str] | None = None  # Pattern only for resource templates, others are None


TEMPLATE_PARAM_REGEX = re.compile(r"{(\w+)}")


class ResourceManager:
    """
    ResourceManager is responsible for registration and execution of MCP resource handlers.

    The Model Context Protocol (MCP) provides a standardized way for servers to expose resources
    that provide context to language models. Each resource is uniquely identified by a URI and can
    represent files, database schemas, API responses, or any application-specific data. Resources
    are application-driven—host applications determine how to incorporate context based on their needs.

    Resources can be static (with fixed URIs) or templated (with parameterized URIs). Resource
    contents can be text or binary data, with optional MIME type specification. Resources also
    support annotations (audience, priority) to provide hints about usage and importance.

    The ResourceManager can be used as a decorator (@mcp.resource(uri)) or programmatically via the
    mcp.resource.add(), mcp.resource.list(), mcp.resource.list_templates(), mcp.resource.read(),
    mcp.resource.read_by_name(), mcp.resource.remove() methods.

    When a resource handler is added, its name and description are automatically inferred from
    the handler function. You can override these by passing explicit parameters. For resource templates,
    the URI parameters (e.g., {path}, {id}) must exactly match the function parameters.

    Resources vs Resource Templates:
    - Resources: Fixed URI, no parameters (e.g., "file:///config.json", "https://api.example.com/data")
    - Resource Templates: Parameterized URI with placeholders (e.g., "file:///{path}", "db://tables/{table}")

    Common URI Schemes:
    - file:// - Filesystem or filesystem-like resources
    - https:// - Web-accessible resources (when client can fetch directly)
    - git:// - Git version control integration
    - Custom schemes following RFC 3986

    For more details, see: https://modelcontextprotocol.io/specification/2025-06-18/server/resources

    Example:
        # Static resource
        @mcp.resource("math://constants/pi", mime_type="text/plain")
        def pi_value() -> str:
            return "3.14159"

        # Resource template
        @mcp.resource("file:///{path}", mime_type="text/plain")
        def read_file(path: str) -> str:
            return Path(path).read_text()

        # With annotations
        @mcp.resource("db://schema", annotations={"audience": ["assistant"], "priority": 0.9})
        def database_schema() -> dict:
            return {"tables": ["users", "orders"]}

        # Or programmatically:
        mcp.resource.add(database_schema, "db://schema", mime_type="application/json")
    """

    _resources: dict[str, _ResourceEntry]

    def __init__(self, core: Server):
        """
        Args:
            core: The low-level MCP Server instance to hook into.
        """
        self._resources = {}
        self._hook_core(core)

    def _hook_core(self, core: Server) -> None:
        """Register resource handlers with the MCP core server.

        Args:
            core: The low-level MCP Server instance to hook into.
        """
        core.list_resources()(self._async_list)
        core.list_resource_templates()(self._async_list_templates)
        core.read_resource()(self.read)
        # core.subscribe_resource()(self.get) # TODO: Implement
        # core.unsubscribe_resource()(self.get) # TODO: Implement

    def __call__(
        self, uri: str, **kwargs: Unpack[ResourceDefinition]
    ) -> Callable[[AnyFunction], Resource | ResourceTemplate]:
        """Decorator to add/register a resource handler at the time of handler function definition.

        Each resource must have a unique URI following RFC 3986. Resources are uniquely identified
        by this URI in the MCP protocol. Resource name and description are automatically inferred
        from the handler function. You can override these by passing explicit parameters.

        For resource templates (URIs with placeholders like {param}), the URI parameters must exactly
        match the function parameters. Type annotations are required in the function signature for
        proper parameter extraction.

        Handler functions can return:
        - str (text content) - will use provided mime_type or default to text/plain
        - bytes (binary content) - will be base64-encoded, requires mime_type
        - dict/list (JSON-serializable) - will be JSON-encoded with application/json

        Args:
            uri: The resource URI uniquely identifying this resource. Can be static
                (e.g., "file:///config.json", "https://example.com/data") or templated
                (e.g., "file:///{path}", "db://tables/{table}"). Template parameters in
                curly braces must match function parameter names. Use common URI schemes
                (file://, https://, git://) or define custom schemes following RFC 3986.
            **kwargs: Optional resource definition parameters (name, title, description, mime_type,
                annotations, meta). Parameters are defined in the ResourceDefinition class.

        Returns:
            A decorator function that adds the resource handler.

        Example:
            @mcp.resource("file:///{path}", mime_type="text/plain")
            def read_file(path: str) -> str:
                return Path(path).read_text()

            @mcp.resource("https://example.com/status", annotations={"priority": 1.0})
            def api_status() -> dict:
                return {"status": "ok"}
        """

        def decorator(func: AnyFunction) -> Resource | ResourceTemplate:
            return self.add(func, uri, **kwargs)

        return decorator

    def add(self, func: AnyFunction, uri: str, **kwargs: Unpack[ResourceDefinition]) -> Resource | ResourceTemplate:
        """To programmatically add/register a resource handler function.

        This is useful when the handler function is already defined and you have a function object
        that needs to be registered at runtime.

        Each resource must have a unique URI following RFC 3986. If not provided, the resource name
        and description are automatically inferred from the function's name and docstring. For resource
        templates, URI parameters (in curly braces) are extracted and must exactly match the function
        parameters. Type annotations are required in the function signature for proper parameter extraction.

        Handler functions should return content appropriate for the resource type:
        - Text resources: return str
        - Binary resources: return bytes (will be base64-encoded per MCP spec)
        - Structured data: return dict/list (will be JSON-serialized)

        Args:
            func: The resource handler function. Can be synchronous or asynchronous. Should return
                string, bytes, or any JSON-serializable object.
            uri: The unique resource URI following RFC 3986. Can be static (e.g., "file:///config.json",
                "https://api.example.com/data") or templated (e.g., "file:///{path}", "db://tables/{table}").
                Template parameters in curly braces must match function parameter names. Common URI schemes
                include file://, https://, git://, or custom schemes.
            **kwargs: Optional resource definition parameters to override inferred values
                (name, title, description, mime_type, annotations, meta). Parameters are defined
                in the ResourceDefinition class.

        Returns:
            The registered Resource or ResourceTemplate object.

        Raises:
            PrimitiveError: If a resource with the same name is already registered, if URI is empty,
                if URI parameters don't match function parameters, or if the function isn't properly typed.
        """

        if not uri:
            raise PrimitiveError("URI is required, pass it as part of the definition.")

        resource_func = MCPFunc(func, kwargs.get("name"))
        if resource_func.name in self._resources:
            raise PrimitiveError(f"Resource {resource_func.name} already registered")

        normalized_uri = self._check_similar_resource(uri)

        uri_params = self._get_uri_parameters(uri)
        func_params = self._get_func_parameters(resource_func)

        if uri_params or func_params:
            # Resource Template
            if uri_params != func_params:
                raise PrimitiveError(
                    f"Mismatch between URI parameters {uri_params} and function parameters {func_params}"
                )

            resource = ResourceTemplate(
                name=resource_func.name,
                title=kwargs.get("title", None),
                uriTemplate=uri,
                description=kwargs.get("description", resource_func.doc),
                mimeType=kwargs.get("mime_type", None),
                annotations=kwargs.get("annotations", None),
                _meta=kwargs.get("meta", None),
            )

            resource_details = _ResourceEntry(
                resource=resource,
                func=resource_func,
                normalized_uri=normalized_uri,
                uri_pattern=_uri_to_pattern(uri),
            )
        else:
            # Resource
            resource = Resource(
                name=resource_func.name,
                title=kwargs.get("title", None),
                uri=uri,  # type: ignore[arg-type]
                description=kwargs.get("description", resource_func.doc),
                mimeType=kwargs.get("mime_type", None),
                annotations=kwargs.get("annotations", None),
                _meta=kwargs.get("meta", None),
            )

            resource_details = _ResourceEntry(
                resource=resource,
                func=resource_func,
                normalized_uri=uri,
            )

        self._resources[resource_func.name] = resource_details

        return resource

    def _check_similar_resource(self, uri: str) -> str:
        """Check if a similar resource is already registered.

        Normalizes the URI by replacing template parameters with a sentinel value
        to detect duplicate resources with different parameter names.

        Args:
            uri: The URI to check.

        Returns:
            The normalized URI.

        Raises:
            PrimitiveError: If a similar resource is already registered.
        """

        normalized_uri = TEMPLATE_PARAM_REGEX.sub("|", uri)

        for r in self._resources.values():
            if r.normalized_uri == normalized_uri:
                raise PrimitiveError(f"Resource {uri} already registered under the name {r.resource.name}")

        return normalized_uri

    def _get_uri_parameters(self, uri: str) -> set[str]:
        """Extract parameter names from a URI template.

        Args:
            uri: The URI template (e.g., "file:///{path}/{name}").

        Returns:
            A set of parameter names found in the URI (e.g., {"path", "name"}).
        """
        return set(TEMPLATE_PARAM_REGEX.findall(uri))

    def _get_func_parameters(self, func: MCPFunc) -> set[str]:
        """Extract parameter names from a function signature.

        Args:
            func: The MCPFunc wrapper containing the function's input schema.

        Returns:
            A set of parameter names from the function signature.
        """
        properties: dict[str, Any] = func.input_schema.get("properties", {})
        return set(properties.keys())

    def remove(self, name: str) -> Resource | ResourceTemplate:
        """Remove a resource by name.

        Args:
            name: The name of the resource to remove.

        Returns:
            The removed Resource or ResourceTemplate object.

        Raises:
            PrimitiveError: If the resource is not found.
        """
        if name not in self._resources:
            raise PrimitiveError(f"Unknown resource: {name}")

        return self._resources.pop(name).resource

    def list(self) -> builtins.list[Resource]:
        """List all registered static resources.

        Returns:
            A list of all registered Resource objects (excludes resource templates).
        """
        return [r.resource for r in self._resources.values() if isinstance(r.resource, Resource)]

    async def _async_list(self) -> builtins.list[Resource]:
        """Async wrapper for list().

        Returns:
            A list of all registered Resource objects.
        """
        return self.list()

    def list_templates(self) -> builtins.list[ResourceTemplate]:
        """List all registered resource templates.

        Returns:
            A list of all registered ResourceTemplate objects (excludes static resources).
        """
        return [r.resource for r in self._resources.values() if isinstance(r.resource, ResourceTemplate)]

    async def _async_list_templates(self) -> builtins.list[ResourceTemplate]:
        """Async wrapper for list_templates().

        Returns:
            A list of all registered ResourceTemplate objects.
        """
        return self.list_templates()

    async def read_by_name(self, name: str, args: dict[str, str] | None = None) -> Iterable[ReadResourceContents]:
        """Read a resource by its registered name.

        Executes the resource handler function with the provided arguments, validates them,
        and returns the resource content. It can be programmatically called like
        `mcp.resource.read_by_name("my_resource", {"path": "file.txt"})`.

        Args:
            name: The name of the resource to read.
            args: Optional dictionary of arguments to pass to the resource handler.
                Required for resource templates, ignored for static resources.

        Returns:
            An iterable of ReadResourceContents containing the resource data and MIME type.

        Raises:
            ResourceNotFoundError: If the resource is not found.
            MCPRuntimeError: If an error occurs during resource execution.
        """
        if name not in self._resources:
            raise ResourceNotFoundError(f"Resource {name} not found", data={"name": name})

        details = self._resources[name]
        return await self._read_resource(details, args)

    async def read(self, uri: AnyUrl | str) -> Iterable[ReadResourceContents]:
        """Read a resource by its URI, as specified in the MCP resources/read protocol.

        This method handles the MCP resources/read request - finding a matching resource (static or
        template) for the given URI, executing the handler function with extracted parameters, and
        returning the resource content per the MCP specification. It can also be programmatically called
        like `mcp.resource.read("file:///path/to/file.txt")`.


        For static resources, performs exact URI matching. For resource templates, performs pattern
        matching and extracts URI parameters to pass to the handler function.

        Args:
            uri: The unique URI identifying the resource to read. Can be a static URI (exact match)
                or a URI that matches a template pattern (e.g., "file:///path/to/file.txt" matching
                the template "file:///{path}"). URIs should follow RFC 3986.

        Returns:
            An iterable of ReadResourceContents containing the resource data (text or blob), MIME type,
            and other metadata per the MCP protocol.

        Raises:
            ResourceNotFoundError: If no matching resource is found for the URI (returns -32002 error per spec).
            MCPRuntimeError: If an error occurs during resource execution.
        """
        uri = str(uri)

        details, args = self._find_matching_resource(uri)
        return await self._read_resource(details, args)

    async def _read_resource(
        self, details: _ResourceEntry, args: dict[str, str] | None
    ) -> Iterable[ReadResourceContents]:
        """Execute a resource handler and convert the result to ReadResourceContents.

        Args:
            details: The resource details containing the handler function and metadata.
            args: Optional dictionary of arguments for the handler function.

        Returns:
            An iterable of ReadResourceContents with the resource content and MIME type.

        Raises:
            MCPRuntimeError: If an error occurs during resource execution or conversion.
        """
        try:
            result = await details.func.execute(args)

            content = self._convert_result(result)
            logger.debug("Resource %s handled with args %s", details.resource.name, args)

            return [ReadResourceContents(content=content, mime_type=details.resource.mimeType)]
        except InvalidArgumentsError:
            raise
        except Exception as e:
            msg = f"Error reading resource {details.resource.name}: {e}"
            logger.exception(msg)
            raise MCPRuntimeError(msg) from e

    def _convert_result(self, result: Any) -> str | bytes:
        """Convert resource handler results to string or bytes content.

        Per the MCP spec, resource contents can be either text or binary:
        - Text content: returned as string with text field in response
        - Binary content: returned as bytes (will be base64-encoded with blob field in response)

        Supports multiple return types:
        - bytes (used as-is, will be base64-encoded per spec)
        - str (used as-is, returned as text content)
        - Other types (JSON-serialized to string)

        Args:
            result: The return value from a resource handler function.

        Returns:
            String or bytes content ready for transmission per MCP protocol.
        """
        if isinstance(result, bytes) or isinstance(result, str):
            content = result
        else:
            content = pydantic_core.to_json(result, fallback=str, indent=2).decode()

        return content

    def _find_matching_resource(self, uri: str) -> tuple[_ResourceEntry, dict[str, str] | None]:
        """Find a resource that matches the given URI.

        First attempts an exact match for static resources, then tries pattern matching
        for resource templates.

        Args:
            uri: The URI to match.

        Returns:
            A tuple of (resource_details, extracted_args). For static resources, args will be None.

        Raises:
            ResourceNotFoundError: If no matching resource is found.
        """
        # Find exact match
        for r in self._resources.values():
            if r.normalized_uri == uri and isinstance(r.resource, Resource):
                return r, None

        # Find with pattern matching
        for r in self._resources.values():
            if r.uri_pattern and (match := r.uri_pattern.match(uri)):
                return r, match.groupdict()

        raise ResourceNotFoundError("Resource not found", data={"uri": uri})


def _uri_to_pattern(uri: str) -> re.Pattern[str]:
    """Convert a URI template to a compiled regular expression pattern.

    Template parameters (e.g., {path}, {id}) are converted to named capture groups
    that match non-slash characters. The rest of the URI is escaped for literal matching.

    Args:
        uri: The URI template (e.g., "file:///{path}/{name}").

    Returns:
        A compiled regex pattern that matches URIs and extracts parameters.

    Example:
        >>> pattern = _uri_to_pattern("file:///{path}/{name}")
        >>> match = pattern.match("file:///documents/report.txt")
        >>> match.groupdict()
        {'path': 'documents', 'name': 'report.txt'}
    """
    # Replace {...} placeholders with a sentinel, escape the rest, then restore named groups
    SENT = "\x00"  # unlikely to appear in templates
    # Protect placeholders so re.escape doesn't touch the braces
    protected = re.sub(r"\{(\w+)\}", lambda m: f"{SENT}{m.group(1)}{SENT}", uri)
    escaped = re.escape(protected)
    # Turn sentinels back into named groups that match a single path segment
    pattern_str = re.sub(
        rf"{re.escape(SENT)}(\w+){re.escape(SENT)}",
        r"(?P<\1>[^/]+)",
        escaped,
    )
    return re.compile(pattern_str + r"$")  # equivalent to fullmatch
