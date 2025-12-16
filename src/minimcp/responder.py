import json
import logging
from operator import attrgetter

import mcp.types as types

from minimcp.limiter import TimeLimiter
from minimcp.types import Message, Send
from minimcp.utils import json_rpc

logger = logging.getLogger(__name__)


class Responder:
    """
    Responder enables message handlers to send notifications back to the client.

    The Responder is available in the handler context via mcp.context.get_responder()
    and provides methods for sending server-to-client notifications, including
    progress updates during long-running operations.

    The responder automatically resets the idle timeout when sending notifications,
    ensuring the handler doesn't time out while actively communicating with the client.
    """

    _request: Message
    _progress_token: types.ProgressToken | None
    _time_limiter: TimeLimiter

    _send: Send

    def __init__(self, request: Message, send: Send, time_limiter: TimeLimiter):
        """
        Args:
            request: The incoming message that triggered the handler.
            send: The send function for transmitting messages to the client.
            time_limiter: The TimeLimiter for managing handler idle timeout.
        """
        self._request = request
        self._progress_token = self._get_progress_token(request)

        self._send = send
        self._time_limiter = time_limiter

    def _get_progress_token(self, request: Message) -> types.ProgressToken | None:
        """Extract the progress token from the request metadata, if present."""
        try:
            client_request = types.ClientRequest.model_validate(json.loads(request))
            return attrgetter("params.meta.progressToken")(client_request.root)
        except Exception:
            return None

    async def report_progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> types.ProgressToken | None:
        """Report progress for the current operation to the client.

        This method sends a progress notification to the client, useful for long-running
        operations where you want to keep the client informed. The notification is only
        sent if the client provided a progress token in the request metadata.

        The idle timeout is automatically reset when sending the progress notification.

        Args:
            progress: Current progress value (e.g., 24 for 24 items processed).
            total: Optional total value (e.g., 100 for total items). Useful for
                calculating completion percentage.
            message: Optional human-readable message to display to the user
                (e.g., "Processing file 24 of 100").

        Returns:
            The progress token if the notification was sent successfully, None otherwise.
            Returns None if no progress token was provided in the request.
        """

        if self._progress_token is None:
            logger.warning("report_progress failed: Progress token is not available.")
            return None

        notification = types.ServerNotification(
            types.ProgressNotification(
                method="notifications/progress",  # TODO: Remove once python-sdk/pull/1292 is merged.
                params=types.ProgressNotificationParams(
                    progressToken=self._progress_token,
                    progress=progress,
                    total=total,
                    message=message,
                ),
            )
        )

        await self.send_notification(notification)

        return self._progress_token

    async def send_notification(self, notification: types.ServerNotification) -> None:
        """Send a notification to the client.

        Notifications are one-way messages from the server to the client that do not
        expect a response. This enables bidirectional communication in MiniMCP servers,
        allowing handlers to proactively push updates to the client.

        The idle timeout is automatically reset when sending notifications, ensuring
        the handler remains active while communicating with the client.

        Args:
            notification: The server notification to send. Common notification types
                include progress notifications, log messages, and resource updates etc.
        """
        logger.debug("Sending notification: %s", notification)
        message = json_rpc.build_notification_message(notification)

        # Reset time limiter
        self._time_limiter.reset()

        # Just call the sender with the message and let transport layer handle the rest.
        await self._send(message)
