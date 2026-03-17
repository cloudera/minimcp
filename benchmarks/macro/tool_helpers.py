from collections.abc import Awaitable, Callable

from mcp import ClientSession
from mcp.types import CallToolResult

from benchmarks.core.mcp_server_benchmark import BenchmarkIndex
from benchmarks.core.sample_tools import compute_all_prime_factors

# --- Benchmark Targets ---


async def sync_benchmark_target(client: ClientSession, index: BenchmarkIndex) -> CallToolResult:
    n = 100 + index.iteration_idx * 100 + index.concurrency_idx * 10
    return await client.call_tool("compute_all_prime_factors", {"n": n})


async def io_bound_async_benchmark_target(client: ClientSession, index: BenchmarkIndex) -> CallToolResult:
    n = 100 + index.iteration_idx * 100 + index.concurrency_idx * 10
    return await client.call_tool("io_bound_compute_all_prime_factors", {"n": n})


async def noop_benchmark_target(client: ClientSession, index: BenchmarkIndex) -> CallToolResult:
    n = 100 + index.iteration_idx * 100 + index.concurrency_idx * 10
    return await client.call_tool("noop_tool", {"n": n})


# --- Result Validators ---


# Pre-compute the expected results for each (tool_name, iteration_idx, concurrency_idx) combination.
_result_map: dict[tuple[str, int, int], int] = {}

for iteration_idx in range(50):
    for concurrency_idx in range(300):
        n = 100 + iteration_idx * 100 + concurrency_idx * 10
        factor_count = compute_all_prime_factors(n)
        _result_map[("compute_all_prime_factors", iteration_idx, concurrency_idx)] = factor_count
        _result_map[("io_bound_compute_all_prime_factors", iteration_idx, concurrency_idx)] = factor_count
        _result_map[("noop_tool", iteration_idx, concurrency_idx)] = n


def result_validator(tool_name: str) -> Callable[[CallToolResult, BenchmarkIndex], Awaitable[bool]]:
    """Return a validator for the given tool name."""

    async def _validator(result: CallToolResult, index: BenchmarkIndex) -> bool:
        expected_result = _result_map[(tool_name, index.iteration_idx, index.concurrency_idx)]
        return result.structuredContent is not None and (result.structuredContent["result"] == expected_result)

    return _validator
