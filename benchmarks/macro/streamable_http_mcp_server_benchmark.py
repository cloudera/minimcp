# isort: off
from benchmarks.macro.servers import fastmcp_http_server, minimcp_streamable_http_server
# isort: on

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from types import ModuleType

import anyio
import psutil
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from benchmarks.configs import HTTP_MCP_PATH, LOADS, REPORTS_DIR, SERVER_HOST, SERVER_PORT
from benchmarks.core.mcp_server_benchmark import BenchmarkIndex, MCPServerBenchmark
from benchmarks.macro.tool_helpers import async_benchmark_target, result_validator, sync_benchmark_target
from tests.integration.helpers.http import until_available, url_available
from tests.integration.helpers.process import run_module


@asynccontextmanager
async def create_client_server(server_module: ModuleType) -> AsyncGenerator[tuple[ClientSession, psutil.Process], None]:
    """
    Create a streamable HTTP client for the given server module.
    """

    server_url: str = f"http://{SERVER_HOST}:{SERVER_PORT}{HTTP_MCP_PATH}"
    default_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    if await url_available(server_url):
        raise RuntimeError(f"Server is already running at {server_url}")

    async with run_module(server_module) as process:
        await until_available(server_url)
        async with streamablehttp_client(server_url, headers=default_headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session, process


async def http_benchmark(
    name: str,
    target: Callable[[ClientSession, BenchmarkIndex], Awaitable[CallToolResult]],
    result_file_path: str,
) -> None:
    benchmark = MCPServerBenchmark[CallToolResult](LOADS, name)

    await benchmark.run(
        "fastmcp",
        partial(create_client_server, fastmcp_http_server),
        target,
        result_validator,
    )

    await benchmark.run(
        "minimcp",
        partial(create_client_server, minimcp_streamable_http_server),
        target,
        result_validator,
    )

    await benchmark.write_json(result_file_path)


def main() -> None:
    anyio.run(
        http_benchmark,
        "MCP Server with Streamable HTTP transport - Benchmark with synchronous tool calls",
        sync_benchmark_target,
        f"{REPORTS_DIR}/streamable_http_mcp_server_sync_benchmark_results.json",
    )
    anyio.run(
        http_benchmark,
        "MCP Server with Streamable HTTP transport - Benchmark with asynchronous tool calls",
        async_benchmark_target,
        f"{REPORTS_DIR}/streamable_http_mcp_server_async_benchmark_results.json",
    )


if __name__ == "__main__":
    main()
