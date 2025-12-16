import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, NamedTuple
from unittest.mock import ANY, AsyncMock, patch

import anyio
import pytest
from mcp.types import LATEST_PROTOCOL_VERSION
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from typing_extensions import override

from minimcp.exceptions import InvalidMessageError
from minimcp.minimcp import MiniMCP
from minimcp.transports.base_http import MEDIA_TYPE_JSON, BaseHTTPTransport, RequestValidationError

pytestmark = pytest.mark.anyio


class MockHTTPTransport(BaseHTTPTransport[Any]):
    """Mock base HTTP transport."""

    RESPONSE_MEDIA_TYPES: frozenset[str] = frozenset[str]([MEDIA_TYPE_JSON])
    SUPPORTED_HTTP_METHODS: frozenset[str] = frozenset[str](["POST"])

    def __init__(self, minimcp: MiniMCP[Any]) -> None:
        super().__init__(minimcp)

    @override
    async def dispatch(self, method: str, headers: Mapping[str, str], body: str, scope: Any = None) -> NamedTuple:
        """Mock dispatch method."""
        raise NotImplementedError("Not implemented")

    @override
    async def starlette_dispatch(self, request: Request, scope: Any = None) -> Response:
        """Mock starlette dispatch method."""
        raise NotImplementedError("Not implemented")

    @override
    def as_starlette(self, path: str = "/", debug: bool = False) -> Starlette:
        """Mock as starlette method."""
        raise NotImplementedError("Not implemented")


class TestBaseHTTPTransport:
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
    def transport(self, mock_handler: AsyncMock) -> BaseHTTPTransport[Any]:
        mcp = AsyncMock(spec=MiniMCP[Any])
        mcp.handle = mock_handler
        return MockHTTPTransport(mcp)

    async def test_handle_post_request_direct(
        self,
        transport: BaseHTTPTransport[Any],
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
        transport: BaseHTTPTransport[Any],
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

        result = await transport._handle_post_request(request_headers, valid_body, None)

        assert result.status_code == HTTPStatus.OK
        assert result.content == notification_response
        assert result.media_type == MEDIA_TYPE_JSON


class TestBaseHTTPTransportHeaderValidation:
    """Test suite for HTTP transport header validation."""

    @pytest.fixture
    def transport(self) -> BaseHTTPTransport[Any]:
        return MockHTTPTransport(AsyncMock(spec=MiniMCP[Any]))

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

    def test_validate_accept_headers_valid(self, transport: BaseHTTPTransport[Any]):
        """Test validate accept headers with valid headers."""
        headers = {"Accept": "application/json, text/plain"}

        transport._validate_accept_headers(headers)

    def test_validate_accept_headers_invalid(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_accept_headers with invalid headers."""
        headers = {"Accept": "text/plain, text/html"}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_validate_accept_headers_missing(self, transport: BaseHTTPTransport[Any]):
        """Test validate accept headers with missing Accept header."""
        headers: dict[str, str] = {}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_validate_accept_headers_with_quality_values(self, transport: BaseHTTPTransport[Any]):
        """Test validate accept headers with quality values."""
        headers = {"Accept": "application/json; q=0.9, text/plain; q=0.1"}

        transport._validate_accept_headers(headers)

    def test_validate_accept_headers_case_insensitive(self, transport: BaseHTTPTransport[Any]):
        """Test validate accept headers is case insensitive."""
        headers = {"Accept": "APPLICATION/JSON"}

        transport._validate_accept_headers(headers)

    def test_validate_content_type_valid(self, transport: BaseHTTPTransport[Any]):
        """Test validate content type with valid content type."""
        headers = {"Content-Type": "application/json"}

        transport._validate_content_type(headers)

    def test_validate_content_type_invalid(self, transport: BaseHTTPTransport[Any]):
        """Test validate content type with invalid content type."""
        headers = {"Content-Type": "text/plain"}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_content_type(headers)

        assert exc_info.value.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    def test_validate_content_type_missing(self, transport: BaseHTTPTransport[Any]):
        """Test validate content type with missing Content-Type header."""
        headers: dict[str, str] = {}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_content_type(headers)

        assert exc_info.value.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    def test_validate_content_type_with_charset(self, transport: BaseHTTPTransport[Any]):
        """Test validate content type with charset parameter."""
        headers = {"Content-Type": "application/json; charset=utf-8"}

        transport._validate_content_type(headers)

    def test_validate_content_type_case_insensitive(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_content_type is case insensitive."""
        headers = {"Content-Type": "APPLICATION/JSON"}

        transport._validate_content_type(headers)

    def test_validate_protocol_version_valid(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_protocol_version with valid version."""
        headers = {"MCP-Protocol-Version": "2025-06-18"}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_invalid(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_protocol_version with invalid version."""
        headers = {"MCP-Protocol-Version": "invalid-version"}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_protocol_version(headers, body)

        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert "Unsupported protocol version" in str(exc_info.value)

    def test_validate_protocol_version_missing_uses_default(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_protocol_version uses default when header is missing."""
        headers: dict[str, str] = {}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_initialize_request_skipped(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_protocol_version skips validation for initialize requests."""
        headers = {"MCP-Protocol-Version": "invalid-version"}
        body = '{"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_malformed_body_ignored(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_protocol_version ignores malformed JSON."""
        headers = {"MCP-Protocol-Version": "2025-06-18"}
        body = "not valid json"

        transport._validate_protocol_version(headers, body)

    def test_validate_protocol_version_case_insensitive_header(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_protocol_version with case insensitive header."""
        headers = {"mcp-protocol-version": "2025-06-18"}
        body = '{"jsonrpc": "2.0", "method": "test", "id": 1}'

        transport._validate_protocol_version(headers, body)

    def test_multiple_needed_content_types(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_accept_headers with multiple needed content types."""
        headers = {"Accept": "application/json, text/event-stream"}
        transport.RESPONSE_MEDIA_TYPES = frozenset[str]({"application/json", "text/event-stream"})

        transport._validate_accept_headers(headers)

    def test_partial_needed_content_types(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_accept_headers when only some needed types are accepted."""
        headers = {"Accept": "application/json"}
        transport.RESPONSE_MEDIA_TYPES = frozenset[str]({"application/json", "text/event-stream"})

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_empty_accept_header(self, transport: BaseHTTPTransport[Any]):
        """Test _validate_accept_headers with empty Accept header."""
        headers = {"Accept": ""}

        with pytest.raises(RequestValidationError) as exc_info:
            transport._validate_accept_headers(headers)

        assert exc_info.value.status_code == HTTPStatus.NOT_ACCEPTABLE

    def test_whitespace_in_headers(self, transport: BaseHTTPTransport[Any]):
        """Test header parsing with extra whitespace."""
        headers = {"Accept": " application/json , text/plain ", "Content-Type": " application/json ; charset=utf-8 "}

        # Accept header test
        transport._validate_accept_headers(headers)

        # Content-Type header test
        transport._validate_content_type(headers)

    async def test_handle_post_request_with_invalid_message_error(self, request_headers: dict[str, str]):
        """Test _handle_post_request when InvalidMessageError is raised."""

        server = MiniMCP[Any](name="test-server", version="1.0.0")
        transport = MockHTTPTransport(server)

        # Create an invalid message that will trigger InvalidMessageError
        invalid_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "test"})

        # Mock handle to raise InvalidMessageError with a response
        error_response = '{"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": 1}'
        with patch.object(server, "handle", side_effect=InvalidMessageError("Invalid", error_response)):
            result = await transport._handle_post_request(request_headers, invalid_message, None)

            assert result.status_code == HTTPStatus.BAD_REQUEST
            assert result.content == error_response
