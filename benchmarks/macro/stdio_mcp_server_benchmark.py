# isort: off
from benchmarks.macro.servers import fastmcp_stdio_server, minimcp_stdio_server
# isort: on

import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from types import ModuleType

import anyio
import psutil
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import CallToolResult

from benchmarks.configs import LOADS, REPORTS_DIR
from benchmarks.core.mcp_server_benchmark import BenchmarkIndex, MCPServerBenchmark
from benchmarks.macro.tool_helpers import async_benchmark_target, result_validator, sync_benchmark_target
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

        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session, server_process


async def stdio_benchmark(
    name: str,
    target: Callable[[ClientSession, BenchmarkIndex], Awaitable[CallToolResult]],
    result_file_path: str,
) -> None:
    benchmark = MCPServerBenchmark[CallToolResult](LOADS, name)

    await benchmark.run(
        "fastmcp",
        partial(create_client_server, fastmcp_stdio_server),
        target,
        result_validator,
    )

    await benchmark.run(
        "minimcp",
        partial(create_client_server, minimcp_stdio_server),
        target,
        result_validator,
    )

    await benchmark.write_json(result_file_path)


def main() -> None:
    anyio.run(
        stdio_benchmark,
        "MCP Server with stdio transport - Benchmark with synchronous tool calls",
        sync_benchmark_target,
        f"{REPORTS_DIR}/stdio_mcp_server_sync_benchmark_results.json",
    )
    anyio.run(
        stdio_benchmark,
        "MCP Server with stdio transport - Benchmark with asynchronous tool calls",
        async_benchmark_target,
        f"{REPORTS_DIR}/stdio_mcp_server_async_benchmark_results.json",
    )


if __name__ == "__main__":
    main()
