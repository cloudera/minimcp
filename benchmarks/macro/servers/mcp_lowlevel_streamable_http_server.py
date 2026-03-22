# isort: off
from benchmarks.core.memory_baseline import get_memory_usage
# isort: on

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from benchmarks.configs import SERVER_HOST, SERVER_PORT
from benchmarks.core.sample_tools import compute_all_prime_factors, io_bound_compute_all_prime_factors, noop_tool

server = Server("mcp-lowlevel")

_TOOLS = [
    types.Tool(
        name="compute_all_prime_factors",
        description=compute_all_prime_factors.__doc__ or "",
        inputSchema={"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
    ),
    types.Tool(
        name="io_bound_compute_all_prime_factors",
        description=io_bound_compute_all_prime_factors.__doc__ or "",
        inputSchema={"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
    ),
    types.Tool(
        name="noop_tool",
        description=noop_tool.__doc__ or "",
        inputSchema={"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
    ),
    types.Tool(
        name="get_memory_usage",
        description="Returns memory usage statistics relative to the process baseline.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Return the list of tools registered on this server."""
    return _TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Dispatch a tool call by name and return the result as structured content."""
    args = arguments or {}
    if name == "compute_all_prime_factors":
        return {"result": compute_all_prime_factors(args["n"])}
    if name == "io_bound_compute_all_prime_factors":
        return {"result": await io_bound_compute_all_prime_factors(args["n"])}
    if name == "noop_tool":
        return {"result": await noop_tool(args["n"])}
    if name == "get_memory_usage":
        return get_memory_usage()
    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    """Run the low-level MCP HTTP server in stateless mode."""
    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        lifespan=lifespan,
        routes=[Mount("/", app=session_manager.handle_request)],
    )
    uvicorn.run(
        starlette_app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        limit_concurrency=1000,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
