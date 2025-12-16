"""Tests for JSON-RPC message building and utility functions."""

import json
from datetime import datetime

import mcp.types as types
import pytest
from pydantic import ValidationError

from minimcp.utils import json_rpc


class TestBuildErrorMessage:
    """Test suite for build_error_message function."""

    def test_build_error_message_basic(self):
        """Test building a basic error message."""
        error = ValueError("test error")
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        error_code = types.INTERNAL_ERROR

        json_message, error_message_str = json_rpc.build_error_message(error, request_message, error_code)

        assert isinstance(json_message, str)
        assert isinstance(error_message_str, str)

        parsed = json.loads(json_message)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["error"]["code"] == error_code
        assert "ValueError" in parsed["error"]["message"]
        assert "test error" in parsed["error"]["message"]

    def test_build_error_message_with_data(self):
        """Test building error message with additional data."""
        error = RuntimeError("runtime error")
        request_message = '{"jsonrpc": "2.0", "id": "req-123", "method": "test"}'
        error_code = types.INTERNAL_ERROR
        data = {"additional": "info", "count": 42}

        json_message, _ = json_rpc.build_error_message(error, request_message, error_code, data=data)

        parsed = json.loads(json_message)
        assert parsed["error"]["data"]["additional"] == "info"
        assert parsed["error"]["data"]["count"] == 42

    def test_build_error_message_includes_metadata(self):
        """Test that error message includes error metadata."""
        error = ValueError("test")
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        error_code = types.INVALID_PARAMS

        json_message, _ = json_rpc.build_error_message(error, request_message, error_code)

        parsed = json.loads(json_message)
        error_data = parsed["error"]["data"]

        assert "errorType" in error_data
        assert error_data["errorType"] == "ValueError"
        assert "errorModule" in error_data
        assert "isoTimestamp" in error_data
        # Should be a valid ISO timestamp
        datetime.fromisoformat(error_data["isoTimestamp"])

    def test_build_error_message_with_stack_trace(self):
        """Test building error message with stack trace included."""
        error = ValueError("test error")
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        error_code = types.INTERNAL_ERROR

        json_message, _ = json_rpc.build_error_message(error, request_message, error_code, include_stack_trace=True)

        parsed = json.loads(json_message)
        assert "stackTrace" in parsed["error"]["data"]
        assert isinstance(parsed["error"]["data"]["stackTrace"], str)
        assert len(parsed["error"]["data"]["stackTrace"]) > 0

    def test_build_error_message_without_stack_trace(self):
        """Test building error message without stack trace."""
        error = ValueError("test error")
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        error_code = types.INTERNAL_ERROR

        json_message, _ = json_rpc.build_error_message(error, request_message, error_code, include_stack_trace=False)

        parsed = json.loads(json_message)
        assert "stackTrace" not in parsed["error"]["data"]

    def test_build_error_message_returns_tuple(self):
        """Test that build_error_message returns a tuple of (message, error_string)."""
        error = ValueError("test")
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        error_code = types.INTERNAL_ERROR

        result = json_rpc.build_error_message(error, request_message, error_code)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)  # JSON message
        assert isinstance(result[1], str)  # Error description

    def test_build_error_message_human_readable_string(self):
        """Test the human-readable error string format."""
        error = ValueError("test error")
        request_message = '{"jsonrpc": "2.0", "id": 123, "method": "test"}'
        error_code = types.INTERNAL_ERROR

        _, error_message_str = json_rpc.build_error_message(error, request_message, error_code)

        assert "ValueError" in error_message_str
        assert "test error" in error_message_str
        assert "123" in error_message_str

    def test_build_error_message_no_request_id(self):
        """Test building error message when request has no ID."""
        error = ValueError("test error")
        request_message = '{"jsonrpc": "2.0", "method": "test"}'
        error_code = types.INVALID_REQUEST

        json_message, error_message_str = json_rpc.build_error_message(error, request_message, error_code)

        parsed = json.loads(json_message)
        assert parsed["id"] == "no-id"
        assert "no-id" in error_message_str

    def test_build_error_message_invalid_request_json(self):
        """Test building error message for invalid JSON request."""
        error = ValueError("parse error")
        request_message = '{"invalid": json}'
        error_code = types.PARSE_ERROR

        json_message, error_message_str = json_rpc.build_error_message(error, request_message, error_code)

        parsed = json.loads(json_message)
        assert parsed["error"]["code"] == types.PARSE_ERROR
        assert parsed["id"] == "no-id"

        assert error_message_str == "ValueError: parse error (Request ID no-id)"

    def test_build_error_message_different_error_codes(self):
        """Test building error messages with different error codes."""
        error = ValueError("test")
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'

        error_codes = [
            types.PARSE_ERROR,
            types.INVALID_REQUEST,
            types.METHOD_NOT_FOUND,
            types.INVALID_PARAMS,
            types.INTERNAL_ERROR,
        ]

        for error_code in error_codes:
            json_message, _ = json_rpc.build_error_message(error, request_message, error_code)
            parsed = json.loads(json_message)
            assert parsed["error"]["code"] == error_code

    def test_build_error_message_merges_data_with_metadata(self):
        """Test that custom data is merged with error metadata."""
        error = ValueError("test")
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        error_code = types.INTERNAL_ERROR
        custom_data = {"custom_field": "custom_value"}

        json_message, _ = json_rpc.build_error_message(error, request_message, error_code, data=custom_data)

        parsed = json.loads(json_message)
        error_data = parsed["error"]["data"]

        # Should have both custom data and metadata
        assert error_data["custom_field"] == "custom_value"
        assert "errorType" in error_data
        assert "errorModule" in error_data
        assert "isoTimestamp" in error_data


class TestGetRequestId:
    """Test suite for get_request_id function."""

    def test_get_request_id_with_integer_id(self):
        """Test extracting integer request ID."""
        request_message = '{"jsonrpc": "2.0", "id": 123, "method": "test"}'
        request_id = json_rpc.get_request_id(request_message)

        assert request_id == 123

    def test_get_request_id_with_string_id(self):
        """Test extracting string request ID."""
        request_message = '{"jsonrpc": "2.0", "id": "test-123", "method": "test"}'
        request_id = json_rpc.get_request_id(request_message)

        assert request_id == "test-123"

    def test_get_request_id_with_null_id(self):
        """Test extracting null request ID returns 'no-id'."""
        request_message = '{"jsonrpc": "2.0", "id": null, "method": "test"}'
        request_id = json_rpc.get_request_id(request_message)

        assert request_id == "no-id"

    def test_get_request_id_without_id(self):
        """Test getting request ID when ID is missing."""
        request_message = '{"jsonrpc": "2.0", "method": "test"}'
        request_id = json_rpc.get_request_id(request_message)

        assert request_id == "no-id"

    def test_get_request_id_invalid_json(self):
        """Test getting request ID from invalid JSON returns 'no-id'."""
        request_message = '{"invalid": json}'
        request_id = json_rpc.get_request_id(request_message)

        assert request_id == "no-id"

    def test_get_request_id_non_dict_json(self):
        """Test getting request ID from non-dict JSON returns 'no-id'."""
        request_message = '["not", "a", "dict"]'
        request_id = json_rpc.get_request_id(request_message)

        assert request_id == "no-id"

    def test_get_request_id_zero(self):
        """Test extracting request ID of 0."""
        request_message = '{"jsonrpc": "2.0", "id": 0, "method": "test"}'
        request_id = json_rpc.get_request_id(request_message)

        assert request_id == 0


class TestIsInitializeRequest:
    """Test suite for is_initialize_request function."""

    def test_is_initialize_request_true(self):
        """Test detecting initialize request."""
        request_message = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}},
            }
        )

        result = json_rpc.is_initialize_request(request_message)
        assert result is True

    def test_is_initialize_request_false_different_method(self):
        """Test detecting non-initialize request."""
        request_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        result = json_rpc.is_initialize_request(request_message)
        assert result is False

    def test_is_initialize_request_false_no_method(self):
        """Test returns False when method is missing."""
        request_message = json.dumps({"jsonrpc": "2.0", "id": 1, "params": {}})

        result = json_rpc.is_initialize_request(request_message)
        assert result is False

    def test_is_initialize_request_invalid_json(self):
        """Test returns False for invalid JSON."""
        request_message = '{"invalid": json}'

        result = json_rpc.is_initialize_request(request_message)
        assert result is False

    def test_is_initialize_request_optimization(self):
        """Test that function uses string check optimization."""
        # Should return False quickly if "initialize" not in string
        request_message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "other", "params": {}})

        result = json_rpc.is_initialize_request(request_message)
        assert result is False

    def test_is_initialize_request_false_positive_prevention(self):
        """Test that function doesn't match 'initialize' in other fields."""
        # "initialize" appears in params, not method
        request_message = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "test", "params": {"note": "initialize stuff"}}
        )

        result = json_rpc.is_initialize_request(request_message)
        assert result is False

    def test_is_initialize_request_notification(self):
        """Test returns False for initialized notification."""
        request_message = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        result = json_rpc.is_initialize_request(request_message)
        assert result is False


class TestCheckJsonrpcVersion:
    """Test suite for check_jsonrpc_version function."""

    def test_check_jsonrpc_version_valid(self):
        """Test checking valid JSON-RPC version."""
        request_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'

        result = json_rpc.check_jsonrpc_version(request_message)
        assert result is True

    def test_check_jsonrpc_version_invalid(self):
        """Test checking invalid JSON-RPC version."""
        request_message = '{"jsonrpc": "1.0", "id": 1, "method": "test"}'

        result = json_rpc.check_jsonrpc_version(request_message)
        assert result is False

    def test_check_jsonrpc_version_missing(self):
        """Test checking when jsonrpc field is missing."""
        request_message = '{"id": 1, "method": "test"}'

        result = json_rpc.check_jsonrpc_version(request_message)
        assert result is False

    def test_check_jsonrpc_version_invalid_json(self):
        """Test checking version with invalid JSON."""
        request_message = '{"invalid": json}'

        result = json_rpc.check_jsonrpc_version(request_message)
        assert result is False

    def test_check_jsonrpc_version_wrong_type(self):
        """Test checking version when jsonrpc is not a string."""
        request_message = '{"jsonrpc": 2.0, "id": 1, "method": "test"}'

        result = json_rpc.check_jsonrpc_version(request_message)
        # Should return False because version should be string "2.0"
        assert result is False

    def test_check_jsonrpc_version_null(self):
        """Test checking when jsonrpc field is null."""
        request_message = '{"jsonrpc": null, "id": 1, "method": "test"}'

        result = json_rpc.check_jsonrpc_version(request_message)
        assert result is False


class TestJSONRPCEnvelope:
    """Test suite for JSONRPCEnvelope internal helper class."""

    def test_jsonrpc_envelope_valid_request(self):
        """Test JSONRPCEnvelope with valid request."""
        message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'

        envelope = json_rpc.JSONRPCEnvelope.model_validate_json(message)

        assert envelope.jsonrpc == "2.0"
        assert envelope.id == 1
        assert envelope.method == "test"

    def test_jsonrpc_envelope_valid_notification(self):
        """Test JSONRPCEnvelope with valid notification."""
        message = '{"jsonrpc": "2.0", "method": "notifications/test"}'

        envelope = json_rpc.JSONRPCEnvelope.model_validate_json(message)

        assert envelope.jsonrpc == "2.0"
        assert envelope.id is None
        assert envelope.method == "notifications/test"

    def test_jsonrpc_envelope_missing_fields(self):
        """Test JSONRPCEnvelope with missing optional fields."""
        message = '{"jsonrpc": "2.0"}'

        envelope = json_rpc.JSONRPCEnvelope.model_validate_json(message)

        assert envelope.jsonrpc == "2.0"
        assert envelope.id is None
        assert envelope.method is None

    def test_jsonrpc_envelope_all_optional(self):
        """Test that all fields in JSONRPCEnvelope are optional."""
        message = "{}"

        envelope = json_rpc.JSONRPCEnvelope.model_validate_json(message)

        assert envelope.jsonrpc is None
        assert envelope.id is None
        assert envelope.method is None

    def test_jsonrpc_envelope_invalid_json(self):
        """Test JSONRPCEnvelope with invalid JSON raises ValidationError."""
        message = '{"invalid": json}'

        with pytest.raises(ValidationError):
            json_rpc.JSONRPCEnvelope.model_validate_json(message)


class TestIntegration:
    """Integration tests for json_rpc module."""

    def test_full_request_response_cycle(self):
        """Test complete request-response cycle."""
        # Build a response
        request_id = 1
        response = types.InitializeResult(
            protocolVersion="2025-06-18",
            capabilities=types.ServerCapabilities(),
            serverInfo=types.Implementation(name="test", version="1.0"),
        )

        response_message = json_rpc.build_response_message(request_id, types.ServerResult(response))

        # Parse and validate
        parsed = json.loads(response_message)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["result"]["protocolVersion"] == "2025-06-18"

        # Extract ID from response
        extracted_id = json_rpc.get_request_id(response_message)
        assert extracted_id == request_id

    def test_full_notification_cycle(self):
        """Test complete notification creation cycle."""
        notification = types.ServerNotification(
            types.ProgressNotification(
                method="notifications/progress",
                params=types.ProgressNotificationParams(
                    progressToken="token-123",
                    progress=75.0,
                    total=100.0,
                ),
            )
        )

        message = json_rpc.build_notification_message(notification)

        # Validate
        parsed = json.loads(message)
        assert parsed["jsonrpc"] == "2.0"
        assert "id" not in parsed  # Notifications don't have ID
        assert parsed["method"] == "notifications/progress"

    def test_full_error_cycle(self):
        """Test complete error message cycle."""
        error = ValueError("Something went wrong")
        request_message = '{"jsonrpc": "2.0", "id": 42, "method": "test"}'
        error_code = types.INTERNAL_ERROR

        error_message, error_string = json_rpc.build_error_message(
            error, request_message, error_code, include_stack_trace=True
        )

        # Validate error message
        parsed = json.loads(error_message)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 42
        assert parsed["error"]["code"] == error_code
        assert "ValueError" in parsed["error"]["message"]
        assert "stackTrace" in parsed["error"]["data"]

        # Validate error string
        assert "ValueError" in error_string
        assert "42" in error_string

    def test_version_checking_integration(self):
        """Test version checking with various message types."""
        valid_message = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        invalid_message = '{"jsonrpc": "1.0", "id": 1, "method": "test"}'

        assert json_rpc.check_jsonrpc_version(valid_message) is True
        assert json_rpc.check_jsonrpc_version(invalid_message) is False

    def test_initialize_request_detection_integration(self):
        """Test initialize request detection integration."""
        init_request = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
        )
        other_request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        assert json_rpc.is_initialize_request(init_request) is True
        assert json_rpc.is_initialize_request(other_request) is False

    def test_is_initialize_request_with_validation_error(self):
        """Test is_initialize_request when ValidationError is raised."""
        # Invalid JSON that contains "initialize" but will fail validation
        invalid_message = '{"initialize": true, "invalid": "structure"}'

        # Should return False when ValidationError is caught
        assert json_rpc.is_initialize_request(invalid_message) is False

    def test_is_initialize_request_without_initialize_keyword(self):
        """Test is_initialize_request when 'initialize' is not in the message."""
        message = '{"jsonrpc": "2.0", "id": 1, "method": "other"}'

        # Should return False early without trying to validate
        assert json_rpc.is_initialize_request(message) is False
