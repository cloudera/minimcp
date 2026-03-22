# isort: off
from benchmarks.core.memory_baseline import get_memory_usage
# isort: on

from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

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


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(_run)
