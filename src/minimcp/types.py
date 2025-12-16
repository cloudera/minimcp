from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Final, Literal

MESSAGE_ENCODING: Final[Literal["utf-8"]] = "utf-8"

# --- MCP response types ---
Message = str


class NoMessage(Enum):
    """
    Represents handler responses without any message.
    https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#sending-messages-to-the-server
    """

    NOTIFICATION = "notification"  # Response to a client notification


# --- Message callback type ---
Send = Callable[[Message], Awaitable[None]]


# --- Additional JSON-RPC error codes ---
"""
Resource not found error (-32002) is defined in the MCP specification but not available as of MCP SDK version 1.24.0.
https://modelcontextprotocol.io/specification/2025-06-18/server/resources#error-handling
"""
RESOURCE_NOT_FOUND = -32002  # Used when a resource is not found as per the MCP specification.
