# isort: off
from benchmarks.core.memory_baseline import get_memory_usage
# isort: on

from mcp.server.fastmcp import FastMCP

from benchmarks.core.sample_tools import async_compute_all_prime_factors, compute_all_prime_factors

mcp = FastMCP(name="FastMCP", log_level="WARNING")

mcp.add_tool(compute_all_prime_factors)
mcp.add_tool(async_compute_all_prime_factors)
mcp.add_tool(get_memory_usage)


if __name__ == "__main__":
    mcp.run()
