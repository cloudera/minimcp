import logging
import sys

import anyio

from minimcp import StdioTransport

from .math_mcp import math_mcp

# Configure logging for the test server
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),  # Log to stderr to avoid interfering with stdio transport
    ],
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the test math server"""

    logger.info("Test MiniMCP: Starting stdio server, listening for messages...")

    transport = StdioTransport[None](math_mcp)
    anyio.run(transport.run)


if __name__ == "__main__":
    main()
