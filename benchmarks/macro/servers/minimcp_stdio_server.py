# isort: off
from benchmarks.core.memory_baseline import get_memory_usage
# isort: on

import anyio

from benchmarks.core.sample_tools import async_compute_all_prime_factors, compute_all_prime_factors
from minimcp import MiniMCP, StdioTransport

mcp = MiniMCP[None](name="MinimCP", max_concurrency=1000)  # Not enforcing concurrency controls for this benchmark

mcp.tool.add(compute_all_prime_factors)
mcp.tool.add(async_compute_all_prime_factors)
mcp.tool.add(get_memory_usage)


def main():
    transport = StdioTransport[None](mcp)
    anyio.run(transport.run)


if __name__ == "__main__":
    main()
