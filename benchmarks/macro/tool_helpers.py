from mcp import ClientSession
from mcp.types import CallToolResult

from benchmarks.core.mcp_server_benchmark import BenchmarkIndex
from benchmarks.core.sample_tools import compute_all_prime_factors

# --- Benchmark Targets ---


async def sync_benchmark_target(client: ClientSession, index: BenchmarkIndex) -> CallToolResult:
    n = 100 + index.iteration_idx * 100 + index.concurrency_idx * 10
    return await client.call_tool("compute_all_prime_factors", {"n": n})


async def async_benchmark_target(client: ClientSession, index: BenchmarkIndex) -> CallToolResult:
    n = 100 + index.iteration_idx * 100 + index.concurrency_idx * 10
    return await client.call_tool("async_compute_all_prime_factors", {"n": n})


# --- Result Validators ---


# Pre-compute the results to speed up validation.
_result_map: dict[tuple[int, int], int] = {}

for iteration_idx in range(50):
    for concurrency_idx in range(300):
        n = 100 + iteration_idx * 100 + concurrency_idx * 10
        _result_map[(iteration_idx, concurrency_idx)] = compute_all_prime_factors(n)


async def result_validator(result: CallToolResult, index: BenchmarkIndex) -> bool:
    return result.structuredContent is not None and (
        result.structuredContent.get("result") == _result_map[(index.iteration_idx, index.concurrency_idx)]
    )
