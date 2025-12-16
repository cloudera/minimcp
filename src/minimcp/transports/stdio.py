import logging
import sys
from io import TextIOWrapper
from typing import Generic

import anyio
import anyio.lowlevel
from mcp import types

from minimcp.exceptions import InvalidMessageError
from minimcp.managers.context_manager import ScopeT
from minimcp.minimcp import MiniMCP
from minimcp.types import MESSAGE_ENCODING, Message, NoMessage
from minimcp.utils import json_rpc

logger = logging.getLogger(__name__)


class StdioTransport(Generic[ScopeT]):
    """stdio transport implementation per MCP specification.
    https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#stdio

    - The server reads JSON-RPC messages from its standard input (stdin)
    - The server sends messages to its standard output (stdout)
    - Messages are individual JSON-RPC requests, notifications, or responses
    - Messages are delimited by newlines and MUST NOT contain embedded newlines
    - The server MUST NOT write anything to stdout that is not a valid MCP message

    **IMPORTANT - Logging Configuration:**
    Applications MUST configure logging to write to stderr (not stdout) to avoid interfering
    with the stdio transport. The specification states: "The server MAY write UTF-8 strings to
    its standard error (stderr) for logging purposes."

    Example logging configuration:
        logging.basicConfig(
            level=logging.DEBUG,
            handlers=[logging.StreamHandler(sys.stderr)]
        )

    Implementation details:
    - The anyio.wrap_file implementation naturally applies backpressure
    - Concurrent message handling via task groups
    - Concurrency management is enforced by MiniMCP
    - Exceptions are formatted as standard MCP errors, and shouldn't cause the transport to terminate
    """

    minimcp: MiniMCP[ScopeT]

    stdin: anyio.AsyncFile[str]
    stdout: anyio.AsyncFile[str]

    def __init__(
        self,
        minimcp: MiniMCP[ScopeT],
        stdin: anyio.AsyncFile[str] | None = None,
        stdout: anyio.AsyncFile[str] | None = None,
    ) -> None:
        """
        Args:
            minimcp: The MiniMCP instance to use.
            stdin: Optional stdin stream to use.
            stdout: Optional stdout stream to use.
        """
        self.minimcp = minimcp

        self.stdin = stdin or anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding=MESSAGE_ENCODING))
        self.stdout = stdout or anyio.wrap_file(
            TextIOWrapper(sys.stdout.buffer, encoding=MESSAGE_ENCODING, line_buffering=True)
        )

    async def write_msg(self, response_msg: Message) -> None:
        """Write a message to stdout.

        Per the MCP stdio transport specification, messages MUST NOT contain embedded newlines.
        This function validates that constraint before writing.

        Args:
            response_msg: The message to write to stdout.

        Raises:
            ValueError: If the message contains embedded newlines (violates stdio spec).
        """
        if "\n" in response_msg or "\r" in response_msg:
            raise ValueError("Messages MUST NOT contain embedded newlines")

        logger.debug("Writing response message to stdio: %s", response_msg)
        await self.stdout.write(response_msg + "\n")

    async def dispatch(self, received_msg: Message) -> None:
        """
        Dispatch an incoming message to the MiniMCP instance, and write the response to stdout.
        Exceptions are formatted as standard MCP errors, and shouldn't cause the transport to terminate.

        Args:
            received_msg: The message to dispatch to the MiniMCP instance
        """

        response: Message | NoMessage | None = None

        try:
            response = await self.minimcp.handle(received_msg, self.write_msg)
        except InvalidMessageError as e:
            response = e.response
        except Exception as e:
            response, error_message = json_rpc.build_error_message(
                e,
                received_msg,
                types.INTERNAL_ERROR,
                include_stack_trace=True,
            )
            logger.exception(f"Unexpected error in stdio transport: {error_message}")

        if isinstance(response, Message):
            await self.write_msg(response)

    async def run(self) -> None:
        """
        Start the stdio transport.
        This will read messages from stdin and dispatch them to the MiniMCP instance, and write
        the response to stdout. The transport must run until the stdin is closed.
        """

        try:
            logger.debug("Starting stdio transport")
            async with anyio.create_task_group() as tg:
                async for line in self.stdin:
                    _line = line.strip()
                    if _line:
                        tg.start_soon(self.dispatch, _line)
        except anyio.ClosedResourceError:
            # Stdin was closed (e.g., during shutdown)
            # Use checkpoint to allow cancellation to be processed
            await anyio.lowlevel.checkpoint()
        finally:
            logger.debug("Stdio transport stopped")
