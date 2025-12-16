import json
from http import HTTPStatus
from typing import Any
from unittest.mock import ANY, AsyncMock

import anyio
import pytest
from mcp.types import LATEST_PROTOCOL_VERSION
from starlette.requests import Request

from minimcp.minimcp import MiniMCP
from minimcp.transports.base_http import MEDIA_TYPE_JSON, RequestValidationError
from minimcp.transports.http import HTTPTransport
from minimcp.types import NoMessage

pytestmark = pytest.mark.anyio


class TestHTTPTransport:
    """Test suite for HTTP transport."""

    @pytest.fixture(autouse=True)
    async def timeout_5s(self):
        """Fail test if it takes longer than 5 seconds."""
        with anyio.fail_after(5):
            yield

    @pytest.fixture
    def accept_content_types(self) -> str:
        return "application/json"

    @pytest.fixture
    def request_headers(self, accept_content_types: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        }

    @pytest.fixture
    def valid_body(self) -> str:
        """Create a valid JSON-RPC request body."""
        return json.dumps({"jsonrpc": "2.0", "method": "test_method", "params": {"test": "value"}, "id": 1})

    @pytest.fixture
    def mock_handler(self) -> AsyncMock:
        """Create a mock handler."""
        return AsyncMock(return_value='{"jsonrpc": "2.0", "result": "success", "id": 1}')

    @pytest.fixture
    def transport(self, mock_handler: AsyncMock) -> HTTPTransport[Any]:
        mcp = AsyncMock(spec=MiniMCP[Any])
        mcp.handle = mock_handler
        return HTTPTransport[Any](mcp)

    async def test_dispatch_post_request_success(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test successful POST request handling."""
        result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == '{"jsonrpc": "2.0", "result": "success", "id": 1}'
        assert result.media_type == MEDIA_TYPE_JSON
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_dispatch_unsupported_method(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of unsupported HTTP methods."""
        result = await transport.dispatch("GET", request_headers, valid_body)

        assert result.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert result.headers is not None
        assert "Allow" in result.headers
        assert "POST" in result.headers["Allow"]
        mock_handler.assert_not_called()

    async def test_dispatch_invalid_content_type(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str, accept_content_types: str
    ):
        """Test handling of invalid content type."""
        headers = {
            "Content-Type": "text/plain",
            "Accept": accept_content_types,
        }

        result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert result.content is not None
        assert "Unsupported Media Type" in str(result.content)
        mock_handler.assert_not_called()

    async def test_dispatch_invalid_accept_header(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str
    ):
        """Test handling of invalid Accept header."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
        }

        result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.NOT_ACCEPTABLE
        assert result.content is not None
        assert "Not Acceptable" in str(result.content)
        mock_handler.assert_not_called()

    async def test_dispatch_no_message_response(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling when handler returns NoMessage."""
        mock_handler.return_value = NoMessage.NOTIFICATION

        result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.ACCEPTED
        assert result.content is None or isinstance(result.content, NoMessage)
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_dispatch_error_response(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of JSON-RPC error responses."""
        error_response = json.dumps(
            {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": 1}
        )
        mock_handler.return_value = error_response

        result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == error_response
        assert result.media_type == MEDIA_TYPE_JSON
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_dispatch_internal_error_response(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of internal error responses."""
        error_response = json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": "Internal error"}, "id": 1})
        mock_handler.return_value = error_response

        result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == error_response
        assert result.media_type == MEDIA_TYPE_JSON

    async def test_dispatch_method_not_found_error(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of method not found errors."""
        error_response = json.dumps(
            {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": 1}
        )
        mock_handler.return_value = error_response

        result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == error_response
        assert result.media_type == MEDIA_TYPE_JSON

    async def test_dispatch_unknown_error_code(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of unknown error codes."""
        error_response = json.dumps({"jsonrpc": "2.0", "error": {"code": -99999, "message": "Unknown error"}, "id": 1})
        mock_handler.return_value = error_response

        result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == error_response
        assert result.media_type == MEDIA_TYPE_JSON

    async def test_dispatch_malformed_response(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of malformed JSON responses."""
        mock_handler.return_value = "not valid json"

        result = await transport.dispatch("POST", request_headers, valid_body)

        # Malformed JSON should result in 500 Internal Server Error
        assert result.status_code == HTTPStatus.OK
        assert result.content == "not valid json"
        assert result.media_type == MEDIA_TYPE_JSON

    async def test_dispatch_missing_headers(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str
    ):
        """Test handling with minimal headers."""
        headers: dict[str, str] = {}

        result = await transport.dispatch("POST", headers, valid_body)

        # Should fail due to missing Accept header first (checked before Content-Type)
        assert result.status_code == HTTPStatus.NOT_ACCEPTABLE
        mock_handler.assert_not_called()

    async def test_dispatch_protocol_version_validation(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str, accept_content_types: str
    ):
        """Test protocol version validation."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": "invalid-version",
        }

        result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.BAD_REQUEST
        assert "Unsupported protocol version" in str(result.content)
        mock_handler.assert_not_called()

    async def test_dispatch_initialize_request_skips_version_check(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, accept_content_types: str
    ):
        """Test that initialize requests skip protocol version validation."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            # No protocol version header
        }

        initialize_body = json.dumps(
            {"jsonrpc": "2.0", "method": "initialize", "params": {"protocolVersion": "2025-06-18"}, "id": 1}
        )

        result = await transport.dispatch("POST", headers, initialize_body)

        assert result.status_code == HTTPStatus.OK
        mock_handler.assert_called_once_with(initialize_body, ANY, None)

    async def test_dispatch_default_protocol_version(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str, accept_content_types: str
    ):
        """Test that default protocol version is used when header is missing."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            # No MCP-Protocol-Version header - should use default
        }

        result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_dispatch_content_type_with_charset(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str, accept_content_types: str
    ):
        """Test Content-Type header with charset parameter."""
        headers: dict[str, str] = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": "2025-06-18",
        }

        result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_dispatch_accept_header_with_quality(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str
    ):
        """Test Accept header with quality values."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json; q=0.9, text/plain; q=0.1, text/event-stream; q=0.2",
            "MCP-Protocol-Version": "2025-06-18",
        }

        result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_dispatch_case_insensitive_headers(
        self, transport: HTTPTransport[Any], mock_handler: AsyncMock, valid_body: str, accept_content_types: str
    ):
        """Test that header checking is case insensitive."""
        headers: dict[str, str] = {
            "Content-Type": "APPLICATION/JSON",
            "Accept": accept_content_types.upper(),
            "MCP-Protocol-Version": "2025-06-18",
        }

        result = await transport.dispatch("POST", headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_handle_post_request_direct(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test the _handle_post_request method directly."""
        result = await transport._handle_post_request(request_headers, valid_body, None)

        assert result.status_code == HTTPStatus.OK
        assert result.content == '{"jsonrpc": "2.0", "result": "success", "id": 1}'
        assert result.media_type == MEDIA_TYPE_JSON
        mock_handler.assert_called_once_with(valid_body, ANY, None)

    async def test_response_without_id(
        self,
        transport: HTTPTransport[Any],
        mock_handler: AsyncMock,
        request_headers: dict[str, str],
        valid_body: str,
    ):
        """Test handling of responses without ID (notifications)."""
        notification_response = json.dumps(
            {
                "jsonrpc": "2.0",
                "result": "success",
                # No ID field
            }
        )
        mock_handler.return_value = notification_response

        result = await transport.dispatch("POST", request_headers, valid_body)

        assert result.status_code == HTTPStatus.OK
        assert result.content == notification_response
        assert result.media_type == MEDIA_TYPE_JSON


class TestHTTPTransportHeaderValidation:
    """Test suite for HTTP transport header validation."""

    @pytest.fixture
    def transport(self) -> HTTPTransport[Any]:
        return HTTPTransport[Any](AsyncMock(spec=MiniMCP[Any]))

    @pytest.fixture
    def accept_content_types(self) -> str:
        return "application/json"

    @pytest.fixture
    def request_headers(self, accept_content_types: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": accept_content_types,
            "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        }

    def test_validate_accept_headers_valid(self, transport: HTTPTransport[Any]):
        """Test validate accept headers with valid headers."""
        headers = {"Accept": "application/json, text/plain"}

        transport._validate_accept_headers(headers)

    def test_validate_accept_headers_invalid(self, transport: HTTPTransport[Any]):
        """Test _validate_accept_headers with invalid headers."""
        headers = {"Accept": "text/plain, text/html"}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_validate_accept_headers_missing(self, transport: HTTPTransport[Any]):
        """Test validate accept headers with missing Accept header."""
        headers: dict[str, str] = {}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_validate_accept_headers_with_quality_values(self, transport: HTTPTransport[Any]):
        """Test validate accept headers with quality values."""
        headers = {"Accept": "application/json; q=0.9, text/plain; q=0.1"}

        transport._validate_accept_headers(headers)

    def test_validate_accept_headers_case_insensitive(self, transport: HTTPTransport[Any]):
        """Test validate accept headers is case insensitive."""
        headers = {"Accept": "APPLICATION/JSON"}

        transport._validate_accept_headers(headers)

    def test_validate_content_type_valid(self, transport: HTTPTransport[Any]):
        """Test validate content type with valid content type."""
        headers = {"Content-Type": "application/json"}

        transport._validate_content_type(headers)

    def test_validate_content_type_invalid(self, transport: HTTPTransport[Any]):
        """Test validate content type with invalid content type."""
        headers = {"Content-Type": "text/plain"}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_content_type(headers)

        assert exc_info.value.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    def test_validate_content_type_missing(self, transport: HTTPTransport[Any]):
        """Test validate content type with missing Content-Type header."""
        headers: dict[str, str] = {}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_content_type(headers)

        assert exc_info.value.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    def test_validate_content_type_with_charset(self, transport: HTTPTransport[Any]):
        """Test validate content type with charset parameter."""
        headers = {"Content-Type": "application/json; charset=utf-8"}

        transport._validate_content_type(headers)

    def test_validate_content_type_case_insensitive(self, transport: HTTPTransport[Any]):
        """Test _validate_content_type is case insensitive."""
        headers = {"Content-Type": "APPLICATION/JSON"}

        transport._validate_content_type(headers)

    def test_validate_protocol_version_valid(self, transport: HTTPTransport[Any]):
        """Test _validate_protocol_version with valid version."""
        headers = {"MCP-Protocol-Version": "2025-06-18"}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_invalid(self, transport: HTTPTransport[Any]):
        """Test _validate_protocol_version with invalid version."""
        headers = {"MCP-Protocol-Version": "invalid-version"}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_protocol_version(headers, body)

        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert "Unsupported protocol version" in str(exc_info.value)

    def test_validate_protocol_version_missing_uses_default(self, transport: HTTPTransport[Any]):
        """Test _validate_protocol_version uses default when header is missing."""
        headers: dict[str, str] = {}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_initialize_request_skipped(self, transport: HTTPTransport[Any]):
        """Test _validate_protocol_version skips validation for initialize requests."""
        headers = {"MCP-Protocol-Version": "invalid-version"}
        body = '{"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_malformed_body_ignored(self, transport: HTTPTransport[Any]):
        """Test _validate_protocol_version ignores malformed JSON."""
        headers = {"MCP-Protocol-Version": "2025-06-18"}
        body = "not valid json"

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_case_insensitive_header(self, transport: HTTPTransport[Any]):
        """Test _validate_protocol_version with case insensitive header."""
        headers = {"mcp-protocol-version": "2025-06-18"}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_multiple_needed_content_types(self, transport: HTTPTransport[Any]):
        """Test _validate_accept_headers with multiple needed content types."""
        headers = {"Accept": "application/json, text/event-stream"}
        transport.RESPONSE_MEDIA_TYPES = frozenset[str]({"application/json", "text/event-stream"})

        transport._validate_accept_headers(headers)

    def test_partial_needed_content_types(self, transport: HTTPTransport[Any]):
        """Test _validate_accept_headers when only some needed types are accepted."""
        headers = {"Accept": "application/json"}
        transport.RESPONSE_MEDIA_TYPES = frozenset[str]({"application/json", "text/event-stream"})

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_empty_accept_header(self, transport: HTTPTransport[Any]):
        """Test _validate_accept_headers with empty Accept header."""
        headers = {"Accept": ""}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_whitespace_in_headers(self, transport: HTTPTransport[Any]):
        """Test header parsing with extra whitespace."""
        headers = {"Accept": " application/json , text/plain ", "Content-Type": " application/json ; charset=utf-8 "}

        # Accept header test
        transport._validate_accept_headers(headers)

        # Content-Type header test
        transport._validate_content_type(headers)

    async def test_starlette_dispatch(self, request_headers: dict[str, str]):
        """Test starlette_dispatch method."""

        server = MiniMCP[Any](name="test-server", version="1.0.0")
        transport = HTTPTransport(server)

        # Create a mock request
        init_message = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        )

        # Mock Starlette request
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(k.lower().encode(), v.encode()) for k, v in request_headers.items()],
        }
        request = Request(scope)
        request._body = init_message.encode()

        response = await transport.starlette_dispatch(request)

        assert response.status_code == HTTPStatus.OK
        assert response.media_type == MEDIA_TYPE_JSON

    async def test_as_starlette(self, request_headers: dict[str, str]):
        """Test as_starlette method."""
        server = MiniMCP[Any](name="test-server", version="1.0.0")
        transport = HTTPTransport(server)

        app = transport.as_starlette(path="/mcp", debug=True)

        # Verify app is created
        assert app is not None
        assert len(app.routes) == 1
