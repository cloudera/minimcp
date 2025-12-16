import traceback
from datetime import datetime
from typing import Any

from mcp.types import (
    ErrorData,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCResponse,
    ServerNotification,
    ServerResult,
)
from pydantic import BaseModel, ValidationError

from minimcp.types import Message

# TODO: Remove once https://github.com/modelcontextprotocol/python-sdk/pull/1310 is merged
JSON_RPC_VERSION = "2.0"


def to_dict(model: BaseModel) -> dict[str, Any]:
    """
    Convert a JSON-RPC Pydantic model to a dictionary.

    Args:
        model: The Pydantic model to convert.

    Returns:
        A dictionary representation of the model.
    """
    return model.model_dump(by_alias=True, exclude_none=True)


def _to_message(model: BaseModel) -> Message:
    return model.model_dump_json(by_alias=True, exclude_none=True)


# --- Build JSON-RPC messages ---


def build_response_message(request_id: str | int, response: ServerResult) -> Message:
    """
    Build a JSON-RPC response message with the given message ID and response.

    Args:
        request_id: The message ID to use.
        response: The response object to build the response message from.

    Returns:
        A JSON-RPC response message string.
    """
    json_rpc_response = JSONRPCResponse(jsonrpc=JSON_RPC_VERSION, id=request_id, result=to_dict(response))
    return _to_message(JSONRPCMessage(json_rpc_response))


def build_notification_message(notification: ServerNotification) -> Message:
    """
    Build a JSON-RPC notification message with the given notification.

    Args:
        notification: The notification object to build the notification message from.

    Returns:
        A JSON-RPC notification message string.
    """
    json_rpc_notification = JSONRPCNotification(jsonrpc=JSON_RPC_VERSION, **to_dict(notification))
    return _to_message(JSONRPCMessage(json_rpc_notification))


def build_error_message(
    error: BaseException,
    request_message: str,
    error_code: int,
    data: dict[str, Any] | None = None,
    include_stack_trace: bool = False,
) -> tuple[Message, str]:
    """
    Build a JSON-RPC error message with the given error code, message ID, and error.

    Args:
        error: The error object to build the error message from.
        request_message: The request message that resulted in the error.
        error_code: The JSON-RPC error code to use. See mcp.types for available codes.
        data: Additional data to include in the error message.
        include_stack_trace: Whether to include the stack trace in the error message.

    Returns:
        A tuple containing the error formatted as a JSON-RPC message and a human-readable string.
    """

    request_id = get_request_id(request_message)
    error_type = error.__class__.__name__
    error_message = f"{error_type}: {error} (Request ID {request_id})"

    # Build error data
    error_metadata: dict[str, Any] = {
        "errorType": error_type,
        "errorModule": error.__class__.__module__,
        "isoTimestamp": datetime.now().isoformat(),
    }

    if include_stack_trace:
        stack_trace = traceback.format_exception(type(error), error, error.__traceback__)
        error_metadata["stackTrace"] = "".join(stack_trace)

    error_data = ErrorData(code=error_code, message=error_message, data={**error_metadata, **(data or {})})

    json_rpc_error = JSONRPCError(jsonrpc=JSON_RPC_VERSION, id=request_id, error=error_data)
    return _to_message(JSONRPCMessage(json_rpc_error)), error_message


# --- Utility functions to extract basic details of out of JSON-RPC message ---


# Using a custom model to extract basic details of out of JSON-RPC message
# as pydantic model_validate_json is better than json.loads.
# This could be further optimized using something like ijson, but would be an unnecessary dependency.
class JSONRPCEnvelope(BaseModel):
    id: int | str | None = None
    method: str | None = None
    jsonrpc: str | None = None


def get_request_id(request_message: str) -> str | int:
    """
    Get the request ID from a JSON-RPC request message string.
    """
    request_id = None
    try:
        request_id = JSONRPCEnvelope.model_validate_json(request_message).id
    except ValidationError:
        pass

    return "no-id" if request_id is None else request_id


def is_initialize_request(request_message: str) -> bool:
    """
    Check if the request message is an initialize request.
    """
    try:
        if "initialize" in request_message:
            return JSONRPCEnvelope.model_validate_json(request_message).method == "initialize"
    except ValidationError:
        pass

    return False


def check_jsonrpc_version(request_message: str) -> bool:
    """
    Check if the JSON-RPC version is valid.
    """
    try:
        return JSONRPCEnvelope.model_validate_json(request_message).jsonrpc == JSON_RPC_VERSION
    except ValidationError:
        return False
