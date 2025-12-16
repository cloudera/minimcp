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
