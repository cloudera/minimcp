# isort: off
from benchmarks.core.memory_baseline import get_memory_usage
# isort: on

import uvicorn

from benchmarks.configs import HTTP_MCP_PATH, SERVER_HOST, SERVER_PORT
from benchmarks.core.sample_tools import async_compute_all_prime_factors, compute_all_prime_factors
from minimcp import MiniMCP, StreamableHTTPTransport

mcp = MiniMCP[None](name="MinimCP", max_concurrency=1000)

mcp.tool.add(compute_all_prime_factors)
mcp.tool.add(async_compute_all_prime_factors)
mcp.tool.add(get_memory_usage)


def main():
    transport = StreamableHTTPTransport[None](mcp)
    uvicorn.run(
        transport.as_starlette(HTTP_MCP_PATH),
        host=SERVER_HOST,
        port=SERVER_PORT,
        limit_concurrency=1000,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
