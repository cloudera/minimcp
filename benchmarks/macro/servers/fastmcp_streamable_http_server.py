# isort: off
from benchmarks.core.memory_baseline import get_memory_usage
# isort: on

from fastmcp import FastMCP

from benchmarks.configs import SERVER_HOST, SERVER_PORT
from benchmarks.core.sample_tools import compute_all_prime_factors, io_bound_compute_all_prime_factors, noop_tool

mcp = FastMCP(name="FastMCP")

mcp.add_tool(compute_all_prime_factors)
mcp.add_tool(io_bound_compute_all_prime_factors)
mcp.add_tool(noop_tool)
mcp.add_tool(get_memory_usage)


if __name__ == "__main__":
    mcp.run(transport="http", host=SERVER_HOST, port=SERVER_PORT, show_banner=False, log_level="WARNING")
