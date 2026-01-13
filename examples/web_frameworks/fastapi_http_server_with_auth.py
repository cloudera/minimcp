#!/usr/bin/env python3

"""
FastAPI HTTP MCP Server with Auth
This example demonstrates how to create a minimal MCP server with FastAPI using HTTP transport. It shows
how to use scope to pass extra information that can be accessed inside the handler functions. It also shows
how to use FastAPI's dependency injection along with MiniMCP. It uses FastAPI's HTTPBasic authentication
middleware to extract the user information from the request.

MiniMCP provides a powerful scope object mechanism, and can be used to pass any type of extra information
to the handler functions.

How to run:
    # Start the server (default: http://127.0.0.1:8000)
    uv run --with fastapi uvicorn examples.minimcp.web_frameworks.fastapi_http_server_with_auth:app
"""

from fastapi import Depends, FastAPI, Request  # pyright: ignore[reportMissingImports]
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # pyright: ignore[reportMissingImports]

from .issue_tracker_mcp import Scope, mcp_transport

# --- FastAPI Application ---
app = FastAPI()
security = HTTPBasic()


@app.post("/mcp")
async def mcp(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    scope = Scope(user_name=credentials.username)
    return await mcp_transport.starlette_dispatch(request, scope)
