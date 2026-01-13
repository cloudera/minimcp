#!/usr/bin/env python3
"""
Test server for HTTP transport integration tests.
"""

import os

import uvicorn
from starlette.applications import Starlette

from minimcp import HTTPTransport, StreamableHTTPTransport

from .math_mcp import math_mcp

SERVER_HOST = os.environ.get("TEST_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("TEST_SERVER_PORT", "30789"))

HTTP_MCP_PATH = "/mcp/"
STREAMABLE_HTTP_MCP_PATH = "/streamable-mcp/"


def main():
    """Main entry point for the test server."""

    http_transport = HTTPTransport[None](math_mcp)
    streamable_http_transport = StreamableHTTPTransport[None](math_mcp)

    # In Starlette, the lifespan events do not run for mounted sub-applications,
    # and this is expected behavior. Hence adding manually.
    app = Starlette(lifespan=streamable_http_transport.lifespan)

    app.mount(HTTP_MCP_PATH, http_transport.as_starlette())
    app.mount(STREAMABLE_HTTP_MCP_PATH, streamable_http_transport.as_starlette())

    uvicorn.run(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
