# isort: off
from benchmarks.macro.servers import fastmcp_stdio_server, mcp_lowlevel_stdio_server, minimcp_stdio_server
# isort: on

import importlib.metadata
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from types import ModuleType

import anyio
import psutil
from mcp import ClientSession, StdioServerParameters, stdio_client

from benchmarks.configs import LOADS, REPORTS_DIR
from benchmarks.core.cpu_affinity import CPU_SPLIT_FRACTION, set_cpu_affinity
from benchmarks.core.mcp_server_benchmark import MCPServerBenchmark, ServerConfig
from benchmarks.macro.scenarios import ToolScenario
from tests.integration.helpers.process import find_process


@asynccontextmanager
async def create_client_server(module: ModuleType) -> AsyncGenerator[tuple[ClientSession, psutil.Process], None]:
    """
    Create a stdio client for the given server file.
    stdio_client would internally create a server subprocess and connect to it.
    """

    module_name = module.__name__

    project_root = Path(__file__).parent.parent
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", module_name],
        env={
            "UV_INDEX": os.environ.get("UV_INDEX", ""),
            "PYTHONPATH": str(project_root.absolute()),
        },
    )

    async with stdio_client(server_params) as (read, write):
        server_process = find_process(module_name)
        if not server_process:
            raise RuntimeError(f"Server process not found for module {module_name}")

        set_cpu_affinity(server_process, CPU_SPLIT_FRACTION, 1.0)

        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session, server_process


def main() -> None:
    set_cpu_affinity(psutil.Process(), 0.0, CPU_SPLIT_FRACTION)

    benchmark = MCPServerBenchmark(
        LOADS,
        servers=[
            ServerConfig(
                "fastmcp",
                partial(create_client_server, fastmcp_stdio_server),
                metadata={"version": importlib.metadata.version("fastmcp")},
            ),
            ServerConfig(
                "mcp-lowlevel",
                partial(create_client_server, mcp_lowlevel_stdio_server),
                metadata={"version": importlib.metadata.version("mcp")},
            ),
            ServerConfig(
                "minimcp",
                partial(create_client_server, minimcp_stdio_server),
                metadata={"version": importlib.metadata.version("minimcp")},
            ),
        ],
        reports_dir=REPORTS_DIR,
    )

    anyio.run(
        benchmark.run,
        "stdio_mcp_server_sync_benchmark_results",
        "MCP Server with stdio transport - Benchmark with synchronous tool calls",
        ToolScenario("compute_all_prime_factors"),
    )
    anyio.run(
        benchmark.run,
        "stdio_mcp_server_io_bound_async_benchmark_results",
        "MCP Server with stdio transport - Benchmark with I/O-bound async tool calls",
        ToolScenario("io_bound_compute_all_prime_factors"),
    )
    anyio.run(
        benchmark.run,
        "stdio_mcp_server_noop_benchmark_results",
        "MCP Server with stdio transport - Benchmark with noop tool calls (protocol overhead only)",
        ToolScenario("noop_tool"),
    )


if __name__ == "__main__":
    main()
