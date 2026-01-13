import logging
import os

import anyio

from minimcp import StdioTransport

from .math_mcp import math_mcp

# Configure logging globally for the demo server
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.environ.get("MCP_SERVER_LOG_FILE", "mcp_server.log")),
        logging.StreamHandler(),  # Also log to stderr
    ],
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logger.info("MiniMCP: Started stdio server, listening for messages...")
    transport = StdioTransport[None](math_mcp)
    anyio.run(transport.run)
