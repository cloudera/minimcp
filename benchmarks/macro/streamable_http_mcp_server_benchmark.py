# isort: off
from benchmarks.macro.servers import (
    fastmcp_streamable_http_server,
    mcp_lowlevel_streamable_http_server,
    minimcp_streamable_http_server,
)
# isort: on

import importlib.metadata
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial
from types import ModuleType

import anyio
import psutil
from httpx import AsyncClient, Limits
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from benchmarks.configs import HTTP_MCP_PATH, LOADS, REPORTS_DIR, SERVER_HOST, SERVER_PORT
from benchmarks.core.cpu_affinity import CPU_SPLIT_FRACTION, set_cpu_affinity
from benchmarks.core.mcp_server_benchmark import MCPServerBenchmark, ServerConfig
from benchmarks.macro.scenarios import ToolScenario
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
        set_cpu_affinity(process, CPU_SPLIT_FRACTION, 1.0)
        await until_available(server_url)
        async with AsyncClient(
            headers=default_headers,
            limits=Limits(max_connections=None, max_keepalive_connections=None),
        ) as client:
            async with streamable_http_client(server_url, http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session, process
                # Workaround: give the streamable_http_client background task time to
                # finish any in-flight POST triggered by ClientSession teardown before
                # the task group is cancelled. See docs/ISSUES.md for details.
                await anyio.sleep(0.5)


def main() -> None:
    set_cpu_affinity(psutil.Process(), 0.0, CPU_SPLIT_FRACTION)

    benchmark = MCPServerBenchmark(
        LOADS,
        servers=[
            ServerConfig(
                "fastmcp",
                partial(create_client_server, fastmcp_streamable_http_server),
                metadata={"version": importlib.metadata.version("fastmcp")},
            ),
            ServerConfig(
                "mcp-lowlevel",
                partial(create_client_server, mcp_lowlevel_streamable_http_server),
                metadata={"version": importlib.metadata.version("mcp")},
            ),
            ServerConfig(
                "minimcp",
                partial(create_client_server, minimcp_streamable_http_server),
                metadata={"version": importlib.metadata.version("minimcp")},
            ),
        ],
        reports_dir=REPORTS_DIR,
    )

    anyio.run(
        benchmark.run,
        "streamable_http_mcp_server_sync_benchmark_results",
        "MCP Server with Streamable HTTP transport - Benchmark with synchronous tool calls",
        ToolScenario("compute_all_prime_factors"),
    )
    anyio.run(
        benchmark.run,
        "streamable_http_mcp_server_io_bound_async_benchmark_results",
        "MCP Server with Streamable HTTP transport - Benchmark with I/O-bound async tool calls",
        ToolScenario("io_bound_compute_all_prime_factors"),
    )
    anyio.run(
        benchmark.run,
        "streamable_http_mcp_server_noop_benchmark_results",
        "MCP Server with Streamable HTTP transport - Benchmark with noop tool calls (protocol overhead only)",
        ToolScenario("noop_tool"),
    )


if __name__ == "__main__":
    main()
