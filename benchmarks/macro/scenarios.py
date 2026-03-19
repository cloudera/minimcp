import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from mcp import ClientSession
from mcp.types import CallToolResult

import benchmarks.core.sample_tools as _sample_tools
from benchmarks.configs import LOADS
from benchmarks.core.mcp_server_benchmark import BenchmarkScenario

_MAX_ITERATIONS = max(load.iterations for load in LOADS)
_MAX_CONCURRENCY = max(load.concurrency for load in LOADS)


def calculate_n(iteration_idx: int, concurrency_idx: int) -> int:
    return 100 + iteration_idx * 100 + concurrency_idx * 10


def _precompute_results(tool_name: str) -> dict[int, Any]:
    fn: Callable[[int], Any] | None = getattr(_sample_tools, tool_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"Tool '{tool_name}' not found in benchmarks.core.sample_tools")

    ns = [calculate_n(i, c) for i in range(_MAX_ITERATIONS) for c in range(_MAX_CONCURRENCY)]

    if inspect.iscoroutinefunction(fn):

        async def _gather() -> list[Any]:
            return await asyncio.gather(*[fn(n) for n in ns])

        results: list[Any] = asyncio.run(_gather())
    else:
        results: list[Any] = [fn(n) for n in ns]

    return dict(zip(ns, results))


class ToolScenario(BenchmarkScenario[CallToolResult]):
    tool_name: str
    _result_map: dict[int, Any]

    def __init__(self, tool_name: str) -> None:
        """
        Args:
            tool_name: The name of the MCP tool to benchmark. Must exist in
                ``benchmarks.core.sample_tools``.
        """

        self.tool_name = tool_name
        self._result_map = _precompute_results(tool_name)

    async def target(self, client: ClientSession, iteration_idx: int, concurrency_idx: int) -> CallToolResult:
        n = calculate_n(iteration_idx, concurrency_idx)
        return await client.call_tool(self.tool_name, {"n": n})

    def validate_result(self, result: CallToolResult, iteration_idx: int, concurrency_idx: int) -> bool:
        n = calculate_n(iteration_idx, concurrency_idx)
        expected = self._result_map[n]
        return result.structuredContent is not None and result.structuredContent["result"] == expected
