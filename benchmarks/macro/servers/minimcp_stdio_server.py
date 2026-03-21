# isort: off
from benchmarks.core.memory_baseline import get_memory_usage
# isort: on

import anyio

from benchmarks.core.sample_tools import compute_all_prime_factors, io_bound_compute_all_prime_factors, noop_tool
from minimcp import MiniMCP, StdioTransport

mcp = MiniMCP[None](name="MinimCP", max_concurrency=-1, idle_timeout=-1)

mcp.tool.add(compute_all_prime_factors)
mcp.tool.add(io_bound_compute_all_prime_factors)
mcp.tool.add(noop_tool)
mcp.tool.add(get_memory_usage)


def main():
    transport = StdioTransport[None](mcp)
    anyio.run(transport.run)


if __name__ == "__main__":
    main()
