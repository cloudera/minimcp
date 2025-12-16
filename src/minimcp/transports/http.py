import logging
from collections.abc import Mapping

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from typing_extensions import override

from minimcp.managers.context_manager import ScopeT
from minimcp.minimcp import MiniMCP
from minimcp.transports.base_http import MEDIA_TYPE_JSON, BaseHTTPTransport, MCPHTTPResponse
from minimcp.types import MESSAGE_ENCODING

logger = logging.getLogger(__name__)


class HTTPTransport(BaseHTTPTransport[ScopeT]):
    """
    HTTP transport implementation for MiniMCP.
    """

    RESPONSE_MEDIA_TYPES: frozenset[str] = frozenset[str]([MEDIA_TYPE_JSON])
    SUPPORTED_HTTP_METHODS: frozenset[str] = frozenset[str](["POST"])

    def __init__(self, minimcp: MiniMCP[ScopeT]) -> None:
        super().__init__(minimcp)

    @override
    async def dispatch(
        self, method: str, headers: Mapping[str, str], body: str, scope: ScopeT | None = None
    ) -> MCPHTTPResponse:
        """
        Dispatch an HTTP request to the MiniMCP server.

        Args:
            method: The HTTP method of the request.
            headers: HTTP request headers.
            body: HTTP request body as a string.
            scope: Optional message scope passed to the MiniMCP server.

        Returns:
            MCPHTTPResponse object with the response from the MiniMCP server.
        """

        logger.debug("Handling HTTP request. Method: %s, Headers: %s", method, headers)

        if method == "POST":
            return await self._handle_post_request(headers, body, scope)
        else:
            return self._handle_unsupported_request()

    @override
    async def starlette_dispatch(self, request: Request, scope: ScopeT | None = None) -> Response:
        """
        Dispatch a Starlette request to the MiniMCP server and return the response as a Starlette response object.

        Args:
            request: Starlette request object.
            scope: Optional message scope passed to the MiniMCP server.

        Returns:
            MiniMCP server response formatted as a Starlette Response object.
        """
        body = await request.body()
        body_str = body.decode(MESSAGE_ENCODING)

        result = await self.dispatch(request.method, request.headers, body_str, scope)

        return Response(result.content, result.status_code, result.headers, result.media_type)

    @override
    def as_starlette(self, path: str = "/", debug: bool = False) -> Starlette:
        """
        Provide the HTTP transport as a Starlette application.

        Args:
            path: The path to the MCP application endpoint.
            debug: Whether to enable debug mode.

        Returns:
            Starlette application.
        """

        route = Route(path, endpoint=self.starlette_dispatch, methods=self.SUPPORTED_HTTP_METHODS)

        logger.info("Creating MCP application at path: %s", path)
        return Starlette(routes=[route], debug=debug)
